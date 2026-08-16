"""The storage backend contract every provider implements.

Storage keys are opaque strings the backend understands (a relative path for the
local provider, an object key for S3/R2). The service layer never
constructs provider-specific paths — it asks the backend to derive a key from a
tenant id + filename (:meth:`FileStorage.build_key`) and treats the result as a
handle to pass back to :meth:`load` / :meth:`delete`.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable


@runtime_checkable
class FileStorage(Protocol):
    """Async, tenant-aware blob storage. Implementations must be stateless."""

    @property
    def name(self) -> str:
        """Provider name (for observability / logging)."""
        ...

    def build_key(self, *, user_id: uuid.UUID, filename: str) -> str:
        """Derive a unique, tenant-scoped storage key for a new upload.

        Deterministically namespaced by ``user_id`` and made unique with a
        random component so two uploads of the same filename never collide.
        """
        ...

    async def save(self, *, key: str, data: bytes) -> None:
        """Persist ``data`` under ``key`` (overwrites if it already exists)."""
        ...

    async def load(self, *, key: str) -> bytes:
        """Return the bytes stored under ``key``. Raises if missing."""
        ...

    async def delete(self, *, key: str) -> None:
        """Remove the object at ``key``. Idempotent — missing is not an error."""
        ...
