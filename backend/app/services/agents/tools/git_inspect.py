"""Green tools: read a git repository's state without changing it.

Three separate tools rather than one `git` tool taking a subcommand. A single
tool whose first argument is the verb would put the choice of git operation in
model output, which is the thing the catalog's tier system is built to avoid:
`git(command="push --force")` is one hallucinated string away from a Red action
wearing a Green tier. Here the verb is the tool, the tier is per-verb, and the
only thing the model supplies is a path and a couple of bounded options.

Git is invoked as a subprocess with an argument **list**, never a shell string,
so a repository path containing spaces or shell metacharacters is data rather
than syntax. Every repo path goes through the workspace boundary first.

`git` itself is not assumed to exist: a machine without it gets a clear message
instead of a FileNotFoundError traceback.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from app.services.agents.tools.context import ToolContext
from app.services.agents.tools.workspace import WorkspaceError, resolve

logger = logging.getLogger(__name__)

# Generous for a cold repo on a spinning disk, short enough that a wedged git
# cannot hold the turn open to the tool executor's own limit.
_GIT_TIMEOUT_SECONDS = 20.0
# Diffs and logs are fed back into a prompt, so they are bounded here as well
# as by the caller's arguments.
_MAX_OUTPUT_CHARS = 20_000
_MAX_LOG_COUNT = 50


class GitToolError(RuntimeError):
    """Git is unavailable, the path is not a repository, or the command failed."""


def _git_path() -> str:
    found = shutil.which("git")
    if found is None:
        raise GitToolError("git is not installed or not on PATH on this machine.")
    return found


async def _run_git(repo: Path, args: list[str]) -> str:
    """Run one git command in ``repo`` and return stdout.

    Uses ``create_subprocess_exec`` (argv list, no shell) so nothing in the
    path or arguments can be interpreted as shell syntax.
    """
    executable = _git_path()
    process = await asyncio.create_subprocess_exec(
        executable,
        "-C",
        str(repo),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=_GIT_TIMEOUT_SECONDS
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        raise GitToolError(
            f"git {args[0]} took longer than {_GIT_TIMEOUT_SECONDS:.0f}s"
        ) from None

    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        # git's own stderr is the most useful thing we can say, but it is
        # untrusted text heading for a prompt, so it is bounded.
        raise GitToolError(detail[:500] or f"git {args[0]} failed")
    return stdout.decode("utf-8", errors="replace")


def _repo(context: ToolContext, args: dict) -> Path:
    """Resolve and validate the repository path from tool arguments."""
    raw = str(args.get("repo_path", "")).strip()
    if not raw:
        raise WorkspaceError("repo_path must not be empty")
    path = resolve(context.workspace, raw, must_exist=True)
    if not path.is_dir():
        raise GitToolError(f"{path} is not a directory")
    return path


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text, False
    return text[:_MAX_OUTPUT_CHARS], True


async def execute_status(context: ToolContext, args: dict) -> dict:
    """Porcelain status for a repository: branch plus changed paths."""
    repo = _repo(context, args)
    raw = await _run_git(repo, ["status", "--porcelain=v1", "--branch"])

    branch = ""
    entries: list[dict[str, str]] = []
    for line in raw.splitlines():
        if line.startswith("##"):
            branch = line[2:].strip()
            continue
        if len(line) > 3:
            entries.append({"state": line[:2].strip(), "path": line[3:]})

    return {
        "repo_path": str(repo),
        "branch": branch,
        "changed": entries[:_MAX_LOG_COUNT],
        "change_count": len(entries),
        "clean": not entries,
    }


async def execute_log(context: ToolContext, args: dict) -> dict:
    """Recent commits as structured records rather than formatted text."""
    repo = _repo(context, args)
    count = max(1, min(int(args.get("count", 10)), _MAX_LOG_COUNT))

    # A unit separator between fields and a record separator between commits:
    # commit subjects routinely contain the characters a naive delimiter would
    # use, and splitting on the wrong one silently corrupts the output.
    fmt = "%H%x1f%an%x1f%aI%x1f%s%x1e"
    raw = await _run_git(repo, ["log", f"-{count}", f"--format={fmt}"])

    commits = []
    for record in raw.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split("\x1f")
        if len(parts) != 4:
            continue
        sha, author, date, subject = parts
        commits.append(
            {"sha": sha[:12], "author": author, "date": date, "subject": subject}
        )

    return {"repo_path": str(repo), "commits": commits, "count": len(commits)}


async def execute_diff(context: ToolContext, args: dict) -> dict:
    """Unified diff of the working tree, or of the staged set."""
    repo = _repo(context, args)
    staged = bool(args.get("staged", False))

    git_args = ["diff", "--no-color"]
    if staged:
        git_args.append("--cached")
    raw = await _run_git(repo, git_args)

    diff, truncated = _truncate(raw)
    return {
        "repo_path": str(repo),
        "staged": staged,
        "diff": diff,
        "truncated": truncated,
        "empty": not raw.strip(),
    }
