"""File service — upload + processing pipeline for the Files System (M6).

Owns validation and the unit of work (commit); repositories flush. The upload
flow is a deterministic pipeline, each stage traced to Langfuse:

1. ``file.upload``  — validate, persist bytes to the storage backend, create row
2. ``file.process`` — extract text from the stored bytes
3. ``file.chunk``   — deterministically chunk the text and store the chunks

The two status fields are independent: ``upload_status`` tracks the bytes,
``processing_status`` tracks the knowledge extraction. A *validation* failure
(size / type) raises before anything is stored. A *processing* failure (a
corrupt PDF, a missing parser) is captured to the log and recorded on the file
(``processing_status = failed`` + ``error_message``) — the upload itself still
succeeds, so the bytes are never lost and processing can be retried later.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    MAX_FILE_SIZE_BYTES,
    SUPPORTED_FILE_MIME_TYPES,
)
from app.core.exceptions import AppError
from app.core.observability import capture_exception
from app.models.enums import ProcessingStatus, UploadStatus
from app.models.file import File
from app.observability import langfuse as langfuse_obs
from app.repositories import file_chunk_repository as chunk_repo
from app.repositories import file_repository as repo
from app.services.files import (
    chunking_service,
    extraction_service,
    indexing_service,
)
from app.services.files.storage.base import FileStorage
from app.services.files.storage.factory import get_file_storage

logger = logging.getLogger(__name__)

# MIME types whose canonical type we accept directly; aliases map onto these.
_MIME_ALIASES: dict[str, str] = {
    "text/x-markdown": "text/markdown",
    "application/x-pdf": "application/pdf",
}
# Extension → MIME fallback when the client sends a generic content type
# (browsers frequently send application/octet-stream for .md / .csv).
_EXTENSION_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".docx": (
        "application/vnd.openxmlformats-officedocument" ".wordprocessingml.document"
    ),
    ".xlsx": ("application/vnd.openxmlformats-officedocument" ".spreadsheetml.sheet"),
}


class FileNotFoundError(AppError):
    """Raised when a file does not exist for this tenant."""

    def __init__(self, file_id: uuid.UUID) -> None:
        super().__init__(
            f"File {file_id} not found.",
            code="file_not_found",
            status_code=404,
        )


class FileTooLargeError(AppError):
    """Raised when an upload exceeds the configured size ceiling."""

    def __init__(self, size_bytes: int) -> None:
        super().__init__(
            f"File is too large ({size_bytes} bytes; " f"max {MAX_FILE_SIZE_BYTES}).",
            code="file_too_large",
            status_code=413,
        )


class EmptyFileError(AppError):
    """Raised when an upload has no bytes."""

    def __init__(self) -> None:
        super().__init__(
            "Uploaded file is empty.",
            code="empty_file",
            status_code=400,
        )


def resolve_mime_type(*, filename: str, content_type: str | None) -> str:
    """Resolve a supported canonical MIME type, or raise 415.

    Honors the client content type (after alias normalization) when supported;
    otherwise falls back to the filename extension. This keeps `.md`/`.csv`
    uploads working even when the browser sends ``application/octet-stream``.
    """
    declared = (content_type or "").split(";")[0].strip().lower()
    declared = _MIME_ALIASES.get(declared, declared)
    if declared in SUPPORTED_FILE_MIME_TYPES:
        return declared
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    inferred = _EXTENSION_MIME.get(ext)
    if inferred is not None:
        return inferred
    raise extraction_service.UnsupportedFileTypeError(
        declared or "application/octet-stream"
    )


async def upload_file(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    original_filename: str,
    content_type: str | None,
    data: bytes,
    storage: FileStorage | None = None,
) -> File:
    """Validate, store, and process an uploaded file. Commits.

    Returns the persisted :class:`File`. The file's ``processing_status``
    reflects whether chunking succeeded (``completed``) or failed (``failed``);
    a failed processing run never raises — the bytes are safely stored.
    """
    storage = storage or get_file_storage()
    size_bytes = len(data)
    if size_bytes == 0:
        raise EmptyFileError()
    if size_bytes > MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(size_bytes)
    mime_type = resolve_mime_type(filename=original_filename, content_type=content_type)

    # Re-uploading the same bytes returns the file already held rather than
    # storing a second copy. Without this, "upload again to refresh it" quietly
    # doubles every chunk in the index, and the same passage comes back twice in
    # every search. Scoped to this user: two people uploading the same public
    # PDF each keep their own, and a shared checksum must never reveal that
    # someone else already has it.
    checksum = hashlib.sha256(data).hexdigest()
    existing = await repo.get_by_checksum(session, user_id=user_id, checksum=checksum)
    if existing is not None:
        logger.info(
            "duplicate upload for user %s; returning file %s", user_id, existing.id
        )
        return existing

    with langfuse_obs.observe_operation(
        "file.upload",
        metadata={
            "filename": original_filename,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
        },
    ):
        key = storage.build_key(user_id=user_id, filename=original_filename)
        await storage.save(key=key, data=data)
        file = await repo.create_file(
            session,
            user_id=user_id,
            filename=key.rsplit("/", 1)[-1],
            original_filename=original_filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            storage_path=key,
            checksum=checksum,
            upload_status=UploadStatus.UPLOADED,
            processing_status=ProcessingStatus.PENDING,
        )
        await session.flush()

    await _process_file(session, file=file, data=data)
    await session.commit()
    await session.refresh(file)
    return file


async def _process_file(session: AsyncSession, *, file: File, data: bytes) -> None:
    """Extract text and store chunks for a file (no commit).

    Transitions ``processing_status`` pending → processing → completed/failed.
    Any failure is recorded on the file and captured to the log; it is **not**
    re-raised so the surrounding upload still succeeds.
    """
    file.processing_status = ProcessingStatus.PROCESSING
    await session.flush()
    started = time.perf_counter()
    try:
        with langfuse_obs.observe_operation(
            "file.process",
            metadata={
                "file_id": str(file.id),
                "mime_type": file.mime_type,
            },
        ) as span:
            segments = extraction_service.extract_segments(
                data=data, mime_type=file.mime_type
            )
            span.update(
                metadata={
                    "segments": len(segments),
                    "extracted_chars": sum(len(s.content) for s in segments),
                }
            )

        with langfuse_obs.observe_operation(
            "file.chunk", metadata={"file_id": str(file.id)}
        ) as span:
            chunks = chunking_service.chunk_segments(segments)
            if chunks:
                await chunk_repo.bulk_create_chunks(
                    session,
                    user_id=file.user_id,
                    file_id=file.id,
                    chunks=[
                        {
                            "chunk_index": c.index,
                            "content": c.content,
                            "token_count": c.token_count,
                            "metadata_json": c.as_metadata(),
                        }
                        for c in chunks
                    ],
                )
            file.chunk_count = len(chunks)
            span.update(
                metadata={
                    "chunk_count": len(chunks),
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }
            )

        # Embedding is part of processing, not a later nicety: a file that is
        # chunked but not embedded is invisible to search, and reporting it as
        # completed would be a lie the user only discovers by asking a question
        # and getting nothing.
        await indexing_service.embed_file_chunks(
            session, user_id=file.user_id, file_id=file.id
        )
        file.indexed_at = datetime.now(UTC)
        file.processing_status = ProcessingStatus.COMPLETED
        file.error_message = None
    except Exception as exc:
        logger.exception("file processing failed for %s", file.id)
        file.processing_status = ProcessingStatus.FAILED
        file.error_message = str(exc)[:1000]
        file.chunk_count = 0
        file.indexed_at = None
        capture_exception(exc, component="file_processing", file_id=str(file.id))
    await session.flush()


async def get_file(
    session: AsyncSession, *, user_id: uuid.UUID, file_id: uuid.UUID
) -> File:
    """Fetch one file or raise 404 (foreign tenants see 404, never 403)."""
    file = await repo.get_file(session, file_id=file_id, user_id=user_id)
    if file is None:
        raise FileNotFoundError(file_id)
    return file


async def list_files(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
    offset: int,
) -> tuple[list[File], int]:
    """List files (newest first)."""
    return await repo.list_files(session, user_id=user_id, limit=limit, offset=offset)


async def delete_file(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    file_id: uuid.UUID,
    storage: FileStorage | None = None,
) -> None:
    """Delete a file: its stored bytes, then its row (cascades chunks). Commits."""
    storage = storage or get_file_storage()
    file = await get_file(session, user_id=user_id, file_id=file_id)
    if file.storage_path:
        try:
            await storage.delete(key=file.storage_path)
        except Exception as exc:
            # Best-effort: a storage delete failure must not block removing the
            # record (the row is the source of truth the user sees). Reported.
            logger.warning("storage delete failed for %s; removing row anyway", file.id)
            capture_exception(exc, component="file_delete", file_id=str(file.id))
    await repo.delete_file(session, file=file)
    await session.commit()


async def reindex_file(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    file_id: uuid.UUID,
    storage: FileStorage | None = None,
) -> File:
    """Re-run extraction, chunking and embedding for a file the user owns.

    The path back from ``failed``, and the way to pick up an improved extractor
    or a changed embedding model without asking the user to upload again.

    Old chunks are deleted first rather than updated in place: chunking is
    deterministic but not stable across code changes — a better extractor
    produces a different number of segments — so merging would leave orphans
    from the previous run in the index, quietly returning text that is no
    longer part of the document.
    """
    file = await get_file(session, user_id=user_id, file_id=file_id)
    if not file.storage_path:
        raise AppError(
            "This file has no stored content to re-index.",
            code="file_not_stored",
            status_code=409,
        )
    storage = storage or get_file_storage()
    data = await storage.load(key=file.storage_path)

    await chunk_repo.delete_for_file(session, user_id=user_id, file_id=file_id)
    file.chunk_count = 0
    file.indexed_at = None
    await session.flush()

    await _process_file(session, file=file, data=data)
    await session.commit()
    await session.refresh(file)
    return file
