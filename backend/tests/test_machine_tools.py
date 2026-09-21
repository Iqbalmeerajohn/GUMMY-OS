"""Tests for the machine-facing tools: git, host files, shell, http_fetch.

These tools reach outside the process, so the tests concentrate on the
refusals. A git tool that reads a repository is easy; a git tool that cannot be
talked into reading *someone else's* repository is the actual requirement.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from app.services.agents.tools import git_inspect, host_files, http_fetch, shell
from app.services.agents.tools.context import ToolContext
from app.services.agents.tools.shell import ShellToolError, parse_command
from app.services.agents.tools.workspace import Workspace, WorkspaceError

# No module-level asyncio mark: pyproject sets asyncio_mode = "auto", so
# coroutine tests are collected as async automatically and the synchronous
# ones below stay synchronous.


def _ctx(root: Path) -> ToolContext:
    """A tool context whose workspace is exactly ``root``.

    ``session`` is None: none of these tools touch the database, and passing a
    real one would hide it if that ever changed.
    """
    return ToolContext(
        session=None,  # type: ignore[arg-type]
        user_id=uuid.uuid4(),
        workspace=Workspace(roots=(root.resolve(),)),
    )


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "work"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "a.txt").write_text("alpha\n", encoding="utf-8")
    (root / "pkg" / "b.txt").write_text("beta\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "private.txt").write_text("no\n", encoding="utf-8")
    return root


# ── host files ───────────────────────────────────────────────────────────────


async def test_read_returns_file_contents(sandbox: Path) -> None:
    out = await host_files.execute_read(
        _ctx(sandbox), {"path": str(sandbox / "pkg" / "a.txt")}
    )
    # The tool reads raw bytes, which is correct — so on Windows the fixture's
    # text-mode write shows up as CRLF. Assert the content, not the platform.
    assert out["content"].strip() == "alpha"
    assert out["truncated"] is False


async def test_read_refuses_outside_the_workspace(sandbox: Path) -> None:
    outside = sandbox.parent / "elsewhere" / "private.txt"
    with pytest.raises(WorkspaceError, match="outside the workspace"):
        await host_files.execute_read(_ctx(sandbox), {"path": str(outside)})


async def test_read_refuses_protected_names(sandbox: Path) -> None:
    with pytest.raises(WorkspaceError, match="protected filename"):
        await host_files.execute_read(_ctx(sandbox), {"path": str(sandbox / ".env")})


async def test_list_is_not_recursive_and_flags_protected(sandbox: Path) -> None:
    out = await host_files.execute_list(_ctx(sandbox), {"path": str(sandbox)})
    names = {entry["name"]: entry for entry in out["entries"]}
    assert names["pkg"]["kind"] == "dir"
    assert names[".env"]["protected"] is True
    # Non-recursive: the children of pkg/ are not present.
    assert "a.txt" not in names


async def test_write_creates_and_reports(sandbox: Path) -> None:
    target = sandbox / "pkg" / "new.txt"
    out = await host_files.execute_write(
        _ctx(sandbox), {"path": str(target), "content": "written\n"}
    )
    assert out["created"] is True
    assert target.read_bytes() == b"written\n"


async def test_write_refuses_outside_the_workspace(sandbox: Path) -> None:
    target = sandbox.parent / "elsewhere" / "injected.txt"
    with pytest.raises(WorkspaceError, match="outside the workspace"):
        await host_files.execute_write(
            _ctx(sandbox), {"path": str(target), "content": "x"}
        )
    assert not target.exists()


async def test_write_requires_string_content(sandbox: Path) -> None:
    with pytest.raises(WorkspaceError, match="content must be a string"):
        await host_files.execute_write(
            _ctx(sandbox), {"path": str(sandbox / "pkg" / "n.txt"), "content": 42}
        )


# ── shell ────────────────────────────────────────────────────────────────────


def test_parse_command_splits_respecting_quotes() -> None:
    assert parse_command('echo "hello world"') == ["echo", "hello world"]


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf / ; echo pwned",
        "cat a.txt && cat b.txt",
        "ls | grep x",
        "echo hi > out.txt",
    ],
)
def test_parse_command_refuses_shell_operators(command: str) -> None:
    """No shell means a pipeline is a refusal, not a silent literal."""
    with pytest.raises(ShellToolError, match="shell operators"):
        parse_command(command)


def test_parse_command_refuses_empty() -> None:
    with pytest.raises(ShellToolError, match="must not be empty"):
        parse_command("   ")


async def test_shell_requires_a_cwd_inside_the_workspace(sandbox: Path) -> None:
    with pytest.raises(WorkspaceError):
        await shell.execute(
            _ctx(sandbox),
            {"command": "python --version", "cwd": str(sandbox.parent / "elsewhere")},
        )


async def test_shell_refuses_an_implicit_cwd(sandbox: Path) -> None:
    with pytest.raises(WorkspaceError, match="never runs against an implicit"):
        await shell.execute(_ctx(sandbox), {"command": "python --version"})


async def test_shell_runs_and_captures_output(sandbox: Path) -> None:
    out = await shell.execute(
        _ctx(sandbox),
        {"command": f'"{os.sys.executable}" -c "print(6*7)"', "cwd": str(sandbox)},
    )
    assert out["ok"] is True
    assert "42" in out["stdout"]
    assert out["exit_code"] == 0


async def test_shell_reports_a_failing_exit_code_as_data(sandbox: Path) -> None:
    """A non-zero exit is an observation, not an exception."""
    out = await shell.execute(
        _ctx(sandbox),
        {
            "command": f'"{os.sys.executable}" -c "raise SystemExit(3)"',
            "cwd": str(sandbox),
        },
    )
    assert out["ok"] is False
    assert out["exit_code"] == 3


async def test_shell_refuses_an_unknown_program(sandbox: Path) -> None:
    with pytest.raises(ShellToolError, match="was not found on PATH"):
        await shell.execute(
            _ctx(sandbox),
            {"command": "definitely-not-a-real-program-xyz", "cwd": str(sandbox)},
        )


# ── git ──────────────────────────────────────────────────────────────────────

_HAS_GIT = shutil.which("git") is not None
requires_git = pytest.mark.skipif(not _HAS_GIT, reason="git is not installed")


@pytest.fixture
def git_repo(sandbox: Path) -> Path:
    repo = sandbox / "repo"
    repo.mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    for args in (
        ["init", "-q"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
    ):
        subprocess.run(["git", *args], cwd=repo, check=True, env=env)  # noqa: S603,S607
    (repo / "tracked.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "."], cwd=repo, check=True, env=env
    )  # noqa: S603,S607
    subprocess.run(  # noqa: S603,S607
        ["git", "commit", "-q", "-m", "initial commit"], cwd=repo, check=True, env=env
    )
    return repo


@requires_git
async def test_git_status_reports_a_clean_tree(sandbox: Path, git_repo: Path) -> None:
    out = await git_inspect.execute_status(_ctx(sandbox), {"repo_path": str(git_repo)})
    assert out["clean"] is True
    assert out["change_count"] == 0


@requires_git
async def test_git_status_reports_a_dirty_tree(sandbox: Path, git_repo: Path) -> None:
    (git_repo / "tracked.txt").write_text("two\n", encoding="utf-8")
    out = await git_inspect.execute_status(_ctx(sandbox), {"repo_path": str(git_repo)})
    assert out["clean"] is False
    assert any(e["path"] == "tracked.txt" for e in out["changed"])


@requires_git
async def test_git_log_parses_structured_commits(sandbox: Path, git_repo: Path) -> None:
    out = await git_inspect.execute_log(
        _ctx(sandbox), {"repo_path": str(git_repo), "count": 5}
    )
    assert out["count"] == 1
    commit = out["commits"][0]
    assert commit["subject"] == "initial commit"
    assert len(commit["sha"]) == 12


@requires_git
async def test_git_diff_shows_uncommitted_changes(
    sandbox: Path, git_repo: Path
) -> None:
    (git_repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    out = await git_inspect.execute_diff(_ctx(sandbox), {"repo_path": str(git_repo)})
    assert out["empty"] is False
    assert "changed" in out["diff"]


@requires_git
async def test_git_refuses_a_repo_outside_the_workspace(
    sandbox: Path, git_repo: Path
) -> None:
    """The boundary applies to repositories exactly as it does to files."""
    narrow = _ctx(sandbox / "pkg")
    with pytest.raises(WorkspaceError, match="outside the workspace"):
        await git_inspect.execute_status(narrow, {"repo_path": str(git_repo)})


# ── http_fetch (SSRF) ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/health",
        "http://localhost:5432/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]:9000/",
        "http://0.0.0.0:80/",
    ],
)
async def test_http_fetch_refuses_internal_addresses(url: str) -> None:
    """Resolved-IP checking, not hostname string matching."""
    with pytest.raises(http_fetch.HttpFetchError, match="not a public address"):
        await http_fetch.fetch(url)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x"])
async def test_http_fetch_refuses_non_http_schemes(url: str) -> None:
    with pytest.raises(http_fetch.HttpFetchError, match="http and https only"):
        await http_fetch.fetch(url)


async def test_http_fetch_refuses_empty_url() -> None:
    with pytest.raises(http_fetch.HttpFetchError, match="must not be empty"):
        await http_fetch.fetch("  ")


async def test_assert_public_url_rejects_unresolvable_host() -> None:
    with pytest.raises(http_fetch.HttpFetchError, match="could not resolve"):
        http_fetch.assert_public_url("http://this-host-should-not-resolve.invalid/path")


def test_shell_stream_truncation_is_bounded() -> None:
    """Output heading for a prompt must be capped."""
    assert shell.MAX_STREAM_CHARS <= 20_000
    assert asyncio.iscoroutinefunction(shell.execute)
