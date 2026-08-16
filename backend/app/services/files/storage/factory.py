"""Construct the configured file-storage backend (cached singleton).

Mirrors the embeddings / LLM factories: the provider is selected by config and
returned behind the :class:`FileStorage` protocol, so callers never depend on a
concrete backend. New backends (r2 / s3) slot in here only.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.services.files.storage.base import FileStorage
from app.services.files.storage.local_provider import LocalFileStorage


@lru_cache
def get_file_storage() -> FileStorage:
    settings = get_settings()
    provider = settings.files_storage_provider.lower()

    if provider == "local":
        return LocalFileStorage(settings.files_storage_dir)

    raise ValueError(
        f"Unknown FILES_STORAGE_PROVIDER {settings.files_storage_provider!r} "
        "(expected one of: local). r2/s3 are planned."
    )
