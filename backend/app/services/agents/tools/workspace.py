"""The workspace boundary — the one place a host path is resolved.

Every tool that touches the machine (git, shell, host file reads and writes)
resolves its path through :func:`resolve`, and nothing else. A tool that takes
a path and does not call this module is a bug.

The boundary exists because the agent's path argument is *model output*, which
is untrusted in exactly the way the tool interface already says tool args are:
a small model emits confidently wrong arguments, and a prompt-injected document
can ask for `../../.ssh/id_rsa` in a tone that sounds like the user. So the
allowlist is configuration, never an argument — there is no tool parameter that
can widen it, and a tool cannot opt out of it.

Three properties it guarantees:

1. **Containment.** The resolved real path must sit inside a configured root.
   Resolution happens with ``Path.resolve()`` *before* the check, so ``..``
   traversal, ``.`` noise and mixed separators collapse first and cannot be
   used to escape.
2. **No symlink escape.** ``resolve()`` follows links, so a symlink inside a
   root that points outside it resolves to its target and then fails the
   containment check, rather than being read through.
3. **Deny by default.** With no roots configured, every call fails closed. An
   empty allowlist means "nothing", never "everything" — the opposite default
   would turn a missing environment variable into full host access.

Sensitive-name refusal is deliberately *not* a security boundary and is
documented as such below: it stops an accident, not an attacker.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

# Filenames that are refused inside an allowed root. This is fat-finger
# protection, not a security control: a determined caller can read the same
# bytes by another name, and `shell_exec` does not consult this list at all.
# It is here because "the agent read your .env while summarising a folder" is
# a plausible accident, and cheap to prevent.
SENSITIVE_NAME_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "*.kdbx",
    "credentials",
    "credentials.*",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
)

# Read caps. A tool result is fed back into a prompt, so an unbounded read is
# both a memory problem and a context-window problem.
MAX_READ_BYTES = 256 * 1024
MAX_WRITE_BYTES = 1024 * 1024
MAX_LISTING_ENTRIES = 500


class WorkspaceError(ValueError):
    """A path is outside the workspace, refused, or unusable."""


@dataclass(frozen=True)
class Workspace:
    """The configured set of roots an agent may touch on this machine."""

    roots: tuple[Path, ...]

    @property
    def configured(self) -> bool:
        return bool(self.roots)

    def describe(self) -> list[str]:
        """Root paths as strings, for diagnostics and tool descriptions."""
        return [str(root) for root in self.roots]


def from_settings() -> Workspace:
    """The workspace configured for this process.

    Read on each call rather than cached at import: tests and the settings
    cache both expect configuration changes to take effect without a reload,
    and parsing a short path list is not worth memoising.
    """
    from app.core.config import get_settings

    return Workspace(roots=parse_roots(get_settings().gummy_workspace_roots))


def parse_roots(raw: str | None) -> tuple[Path, ...]:
    """Parse the configured root list into resolved, existing directories.

    Entries are separated by ``os.pathsep`` (``;`` on Windows, ``:`` elsewhere).
    Unusable entries are dropped rather than raising: one mistyped root should
    cost that root, not every host tool. A root that does not exist is dropped
    for the same reason — it cannot contain anything, so keeping it would only
    produce confusing "outside the workspace" errors later.
    """
    if not raw or not raw.strip():
        return ()

    roots: list[Path] = []
    for entry in raw.split(os.pathsep):
        candidate = entry.strip().strip('"')
        if not candidate:
            continue
        try:
            resolved = Path(candidate).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def is_sensitive_name(name: str) -> bool:
    """True when ``name`` matches a refused filename pattern (case-insensitive)."""
    lowered = name.lower()
    return any(fnmatch.fnmatch(lowered, pattern) for pattern in SENSITIVE_NAME_PATTERNS)


def resolve(
    workspace: Workspace,
    raw_path: str,
    *,
    must_exist: bool = True,
    allow_sensitive: bool = False,
) -> Path:
    """Resolve ``raw_path`` to a real path inside ``workspace``, or raise.

    ``must_exist`` is False for write targets, whose parent must still be
    inside a root — so a write cannot create a file outside the boundary, and
    cannot create one *through* a symlinked parent either.
    """
    if not workspace.configured:
        raise WorkspaceError(
            "No workspace roots are configured, so host paths are unavailable. "
            "Set GUMMY_WORKSPACE_ROOTS to enable them."
        )

    cleaned = (raw_path or "").strip().strip('"')
    if not cleaned:
        raise WorkspaceError("path must not be empty")

    try:
        # strict=False so a not-yet-existing write target still normalises;
        # existence is asserted separately below.
        candidate = Path(cleaned).expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise WorkspaceError(f"could not resolve path {cleaned!r}") from exc

    # Containment is checked against the *resolved* path, after `..` and any
    # symlinks have collapsed, so neither can be used to step outside a root.
    if not _within_roots(candidate, workspace.roots):
        raise WorkspaceError(
            f"{candidate} is outside the workspace. Allowed roots: "
            + ", ".join(workspace.describe())
        )

    if not allow_sensitive and is_sensitive_name(candidate.name):
        raise WorkspaceError(
            f"{candidate.name} matches a protected filename and will not be read "
            "or written by a tool."
        )

    if must_exist:
        if not candidate.exists():
            raise WorkspaceError(f"{candidate} does not exist")
    else:
        parent = candidate.parent
        if not parent.exists():
            raise WorkspaceError(f"{parent} does not exist")
        # Re-check the parent: a write target's parent could itself be a
        # symlink out of the workspace that the earlier check saw only through
        # the unresolved child.
        if not _within_roots(parent.resolve(strict=True), workspace.roots):
            raise WorkspaceError(f"{parent} is outside the workspace")

    return candidate


def _within_roots(candidate: Path, roots: tuple[Path, ...]) -> bool:
    """True when ``candidate`` is a root or sits beneath one."""
    for root in roots:
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        return True
    return False


def read_text(path: Path, *, max_bytes: int = MAX_READ_BYTES) -> tuple[str, bool]:
    """Read up to ``max_bytes`` of ``path`` as text.

    Returns ``(text, truncated)``. Decoding is lenient because these are real
    files on a developer's machine, and failing a whole read over one bad byte
    is less useful than showing the text with that byte replaced.
    """
    if path.is_dir():
        raise WorkspaceError(f"{path} is a directory, not a file")
    data = path.read_bytes()
    truncated = len(data) > max_bytes
    return data[:max_bytes].decode("utf-8", errors="replace"), truncated
