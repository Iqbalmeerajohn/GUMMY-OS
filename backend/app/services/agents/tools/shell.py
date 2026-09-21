"""Red tool: run a shell command inside the workspace.

This is the most dangerous capability in the catalog and it is tiered Red,
which means: never auto-allowed, no standing allowance can cover it, and a
human approves **each individual command** before it runs.

Two design choices are worth stating, because the obvious alternatives are
worse:

**No shell.** The command is parsed with ``shlex`` and executed as an argv
list. That removes the entire class of shell-syntax attacks — ``;``, ``&&``,
backticks, ``$(...)``, redirection and globbing are not special because no
shell ever sees the string. It also means the tool genuinely cannot run a
pipeline, which is a real capability loss and the right trade for a Red tool.

**No command allowlist.** An allowlist here would be security theatre: `python`
and `git` are both plausible allowlist members and both trivially run arbitrary
code. The boundary is the human approval and the workspace root, not a list of
program names that looks reassuring and is not.

Output is captured, bounded, and returned as data. The working directory must
be inside the workspace, so a command cannot start life outside the boundary
even though nothing stops it walking out afterwards — which is precisely why
this needs a person's eyes on every invocation.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
import shutil

from app.services.agents.tools.context import ToolContext
from app.services.agents.tools.workspace import WorkspaceError, resolve

logger = logging.getLogger(__name__)

# Per-stream cap. Output is fed back into a prompt, so a command that prints a
# megabyte must not be able to blow the context window or the audit row.
MAX_STREAM_CHARS = 10_000
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = 120.0


class ShellToolError(RuntimeError):
    """The command could not be parsed, found, or run."""


def parse_command(raw: str) -> list[str]:
    """Split ``raw`` into an argv list, rejecting anything shell-only.

    ``shlex.split`` with ``posix=True`` handles quoting consistently across
    platforms. Shell operators survive as literal tokens rather than being
    interpreted, which would make ``rm -rf / ; echo hi`` run as a single
    program named ``rm`` with a literal ``;`` argument — confusing rather than
    dangerous. Rejecting them outright is clearer than letting that happen.
    """
    cleaned = (raw or "").strip()
    if not cleaned:
        raise ShellToolError("command must not be empty")

    try:
        parts = shlex.split(cleaned, posix=True)
    except ValueError as exc:
        raise ShellToolError(f"could not parse command: {exc}") from exc
    if not parts:
        raise ShellToolError("command must not be empty")

    shell_only = {";", "&&", "||", "|", ">", ">>", "<", "&"}
    offenders = sorted(shell_only.intersection(parts))
    if offenders:
        raise ShellToolError(
            "shell operators ("
            + ", ".join(offenders)
            + ") are not supported — this tool runs a single program with "
            "arguments, not a shell pipeline. Run the steps as separate calls."
        )
    return parts


def _truncate(stream: bytes) -> tuple[str, bool]:
    text = stream.decode("utf-8", errors="replace")
    if len(text) <= MAX_STREAM_CHARS:
        return text, False
    return text[:MAX_STREAM_CHARS], True


async def execute(context: ToolContext, args: dict) -> dict:
    """Run one command in an allowlisted directory and return its output."""
    argv = parse_command(str(args.get("command", "")))

    raw_cwd = str(args.get("cwd", "")).strip()
    if not raw_cwd:
        raise WorkspaceError(
            "cwd must name a directory inside the workspace — this tool never "
            "runs against an implicit working directory."
        )
    cwd = resolve(context.workspace, raw_cwd, must_exist=True)
    if not cwd.is_dir():
        raise WorkspaceError(f"{cwd} is not a directory")

    timeout = float(args.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    timeout = max(1.0, min(timeout, MAX_TIMEOUT_SECONDS))

    program = shutil.which(argv[0], path=None)
    if program is None:
        raise ShellToolError(f"{argv[0]!r} was not found on PATH")

    logger.info("shell_exec running %r in %s", argv, cwd)
    process = await asyncio.create_subprocess_exec(
        program,
        *argv[1:],
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise ShellToolError(
            f"command exceeded {timeout:.0f}s and was killed"
        ) from None

    out_text, out_truncated = _truncate(stdout)
    err_text, err_truncated = _truncate(stderr)

    return {
        "command": " ".join(argv),
        "cwd": str(cwd),
        "exit_code": process.returncode,
        "stdout": out_text,
        "stderr": err_text,
        "truncated": out_truncated or err_truncated,
        # An exit code is not an exception: a failing command is a legitimate
        # observation the agent should be able to reason about.
        "ok": process.returncode == 0,
    }
