"""Host filesystem tools — read and list are Green, write is Yellow.

These are deliberately separate from the Files system. `file_search` and
`doc_read` operate on documents the user uploaded into GUMMY, which are already
tenant-scoped rows in the database. These operate on the *machine*, which has
no tenancy at all, so the boundary has to come from somewhere else — the
workspace allowlist in ``tools/workspace.py``.

The split of tiers follows the catalog's own rule rather than convenience:
reading an allowlisted file is reversible and therefore Green; writing one can
destroy work and is therefore Yellow, which means it goes through the approval
flow and executes only once a human says so.

`workspace_write` refuses to create directories. An agent that misreads a path
should fail, not quietly scatter new folders across a developer's disk; making
the parent is a decision for the person, not the model.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.services.agents.tools.context import ToolContext
from app.services.agents.tools.workspace import (
    MAX_LISTING_ENTRIES,
    MAX_WRITE_BYTES,
    WorkspaceError,
    is_sensitive_name,
    read_text,
    resolve,
)

logger = logging.getLogger(__name__)


async def execute_read(context: ToolContext, args: dict) -> dict:
    """Read one allowlisted file as text."""
    path = resolve(context.workspace, str(args.get("path", "")), must_exist=True)
    text, truncated = read_text(path)
    return {
        "path": str(path),
        "content": text,
        "truncated": truncated,
        "bytes": path.stat().st_size,
    }


async def execute_list(context: ToolContext, args: dict) -> dict:
    """List the immediate children of an allowlisted directory.

    Non-recursive on purpose: a recursive walk of a repository with a
    ``node_modules`` in it produces tens of thousands of entries, none of which
    help a model and all of which cost context.
    """
    path = resolve(context.workspace, str(args.get("path", "")), must_exist=True)
    if not path.is_dir():
        raise WorkspaceError(f"{path} is a file, not a directory")

    entries: list[dict[str, object]] = []
    truncated = False
    for index, child in enumerate(sorted(path.iterdir(), key=_sort_key)):
        if index >= MAX_LISTING_ENTRIES:
            truncated = True
            break
        is_dir = child.is_dir()
        entries.append(
            {
                "name": child.name,
                "kind": "dir" if is_dir else "file",
                # Size is omitted for directories rather than reported as 0,
                # which would read as "empty".
                "bytes": None if is_dir else _safe_size(child),
                # Surfaced so a caller understands why a later read refuses.
                "protected": is_sensitive_name(child.name),
            }
        )

    return {
        "path": str(path),
        "entries": entries,
        "count": len(entries),
        "truncated": truncated,
    }


async def execute_write(context: ToolContext, args: dict) -> dict:
    """Write text to an allowlisted path. Yellow: runs only once approved.

    Overwrites in full. There is no append mode: append and overwrite differ in
    how much they destroy, and a model choosing between them via an argument is
    exactly the kind of decision the tier system exists to take away from it.
    """
    raw_content = args.get("content")
    if not isinstance(raw_content, str):
        raise WorkspaceError("content must be a string")
    encoded = raw_content.encode("utf-8")
    if len(encoded) > MAX_WRITE_BYTES:
        raise WorkspaceError(
            f"content is {len(encoded)} bytes, above the "
            f"{MAX_WRITE_BYTES} byte limit"
        )

    path = resolve(context.workspace, str(args.get("path", "")), must_exist=False)
    if path.is_dir():
        raise WorkspaceError(f"{path} is a directory")

    existed = path.exists()
    previous_bytes = path.stat().st_size if existed else 0
    path.write_bytes(encoded)

    logger.info("workspace_write wrote %d bytes to %s", len(encoded), path)
    return {
        "path": str(path),
        "bytes_written": len(encoded),
        "created": not existed,
        "replaced_bytes": previous_bytes,
    }


def _safe_size(path: Path) -> int | None:
    """File size, or None when it cannot be read (a race or a broken link)."""
    try:
        return path.stat().st_size
    except OSError:
        return None


def _sort_key(path: Path) -> tuple[int, str]:
    """Directories first, then case-insensitive name."""
    return (0 if path.is_dir() else 1, path.name.lower())
