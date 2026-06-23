"""Local filesystem storage backend (dev / single-node default).

Writes blobs under a configurable base directory, namespaced by tenant. Disk
I/O is offloaded to a thread (``asyncio.to_thread``) so the event loop is never
blocked. Keys are relative POSIX-style paths beneath the base dir; the provider
guards against path traversal so a crafted key can never escape it.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path


class LocalFileStorage:
    """Filesystem-backed :class:`FileStorage` rooted at ``base_dir``."""

    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir).resolve()
        self._base.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "local"

    def build_key(self, *, user_id: uuid.UUID, filename: str) -> str:
        # ``<user_id>/<uuid4>__<sanitized name>`` — tenant-namespaced + unique.
        safe = Path(filename).name or "upload"
        return f"{user_id}/{uuid.uuid4()}__{safe}"

    def _resolve(self, key: str) -> Path:
        """Resolve ``key`` to an absolute path, refusing traversal escapes."""
        target = (self._base / key).resolve()
        if self._base not in target.parents and target != self._base:
            raise ValueError(f"Illegal storage key (path traversal): {key!r}")
        return target

    async def save(self, *, key: str, data: bytes) -> None:
        path = self._resolve(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(_write)

    async def load(self, *, key: str) -> bytes:
        path = self._resolve(key)
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, *, key: str) -> None:
        path = self._resolve(key)

        def _unlink() -> None:
            path.unlink(missing_ok=True)

        await asyncio.to_thread(_unlink)
