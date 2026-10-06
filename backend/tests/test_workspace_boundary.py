"""Workspace boundary tests — the containment guarantees, asserted.

Every machine-facing tool resolves its path through ``tools.workspace``, so
these are the tests that decide whether `shell_exec`, `workspace_write` and the
git tools are safe. They are written against the *escape attempts* rather than
the happy path, because containment that only works on well-formed input is not
containment.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.services.agents.tools.workspace import (
    Workspace,
    WorkspaceError,
    is_sensitive_name,
    parse_roots,
    resolve,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    # A sibling the workspace must never reach.
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secrets.txt").write_text("nope\n", encoding="utf-8")
    return Workspace(roots=(root.resolve(),))


def test_unconfigured_workspace_denies_everything(tmp_path: Path) -> None:
    """An empty allowlist means nothing, never everything."""
    empty = Workspace(roots=())
    with pytest.raises(WorkspaceError, match="No workspace roots"):
        resolve(empty, str(tmp_path))


def test_resolves_a_path_inside_a_root(workspace: Workspace) -> None:
    resolved = resolve(workspace, str(workspace.roots[0] / "src" / "main.py"))
    assert resolved.name == "main.py"


def test_rejects_parent_traversal(workspace: Workspace) -> None:
    """``..`` collapses during resolution and then fails containment."""
    escape = workspace.roots[0] / "src" / ".." / ".." / "outside" / "secrets.txt"
    with pytest.raises(WorkspaceError, match="outside the workspace"):
        resolve(workspace, str(escape))


def test_rejects_absolute_path_outside_root(workspace: Workspace) -> None:
    outside = workspace.roots[0].parent / "outside" / "secrets.txt"
    with pytest.raises(WorkspaceError, match="outside the workspace"):
        resolve(workspace, str(outside))


def test_rejects_protected_filenames(workspace: Workspace) -> None:
    """.env sits inside the root and is still refused."""
    with pytest.raises(WorkspaceError, match="protected filename"):
        resolve(workspace, str(workspace.roots[0] / ".env"))


def test_protected_filenames_can_be_opted_into_explicitly(
    workspace: Workspace,
) -> None:
    """The refusal is a guard rail for tools, not an access control."""
    resolved = resolve(
        workspace, str(workspace.roots[0] / ".env"), allow_sensitive=True
    )
    assert resolved.name == ".env"


@pytest.mark.skipif(
    os.name == "nt", reason="creating symlinks on Windows needs elevation"
)
def test_symlink_out_of_the_workspace_is_refused(
    workspace: Workspace, tmp_path: Path
) -> None:
    """Resolution follows the link, so the target is what gets checked."""
    link = workspace.roots[0] / "escape"
    link.symlink_to(tmp_path / "outside")
    with pytest.raises(WorkspaceError, match="outside the workspace"):
        resolve(workspace, str(link / "secrets.txt"))


def test_write_target_need_not_exist_but_its_parent_must(
    workspace: Workspace,
) -> None:
    target = workspace.roots[0] / "src" / "new_file.py"
    assert resolve(workspace, str(target), must_exist=False) == target

    missing_parent = workspace.roots[0] / "nope" / "file.txt"
    with pytest.raises(WorkspaceError, match="does not exist"):
        resolve(workspace, str(missing_parent), must_exist=False)


def test_write_outside_the_workspace_is_refused(
    workspace: Workspace, tmp_path: Path
) -> None:
    target = tmp_path / "outside" / "new.txt"
    with pytest.raises(WorkspaceError, match="outside the workspace"):
        resolve(workspace, str(target), must_exist=False)


def test_empty_path_is_refused(workspace: Workspace) -> None:
    with pytest.raises(WorkspaceError, match="must not be empty"):
        resolve(workspace, "   ")


def test_missing_file_is_refused(workspace: Workspace) -> None:
    with pytest.raises(WorkspaceError, match="does not exist"):
        resolve(workspace, str(workspace.roots[0] / "src" / "ghost.py"))


# ── root parsing ─────────────────────────────────────────────────────────────


def test_parse_roots_handles_empty_and_blank() -> None:
    assert parse_roots(None) == ()
    assert parse_roots("") == ()
    assert parse_roots("   ") == ()


def test_parse_roots_drops_unusable_entries(tmp_path: Path) -> None:
    """One mistyped root costs that root, not every host tool."""
    good = tmp_path / "good"
    good.mkdir()
    raw = os.pathsep.join([str(good), str(tmp_path / "does-not-exist"), ""])
    assert parse_roots(raw) == (good.resolve(),)


def test_parse_roots_drops_files(tmp_path: Path) -> None:
    """A root must be a directory — a file root would contain nothing."""
    afile = tmp_path / "a.txt"
    afile.write_text("x", encoding="utf-8")
    assert parse_roots(str(afile)) == ()


def test_parse_roots_deduplicates(tmp_path: Path) -> None:
    raw = os.pathsep.join([str(tmp_path), str(tmp_path)])
    assert parse_roots(raw) == (tmp_path.resolve(),)


@pytest.mark.parametrize(
    "name",
    [".env", ".env.local", "id_rsa", "server.pem", "credentials.json", ".netrc"],
)
def test_sensitive_names_match(name: str) -> None:
    assert is_sensitive_name(name)


@pytest.mark.parametrize("name", ["main.py", "README.md", "environment.ts"])
def test_ordinary_names_do_not_match(name: str) -> None:
    assert not is_sensitive_name(name)
