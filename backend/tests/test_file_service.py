"""Service tests for the M6 upload + processing pipeline.

Exercises the full store → extract → chunk → persist flow against an in-memory
DB and a temp-dir local storage backend, plus the failure path (a corrupt PDF
is recorded as ``failed`` without losing the bytes or raising).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProcessingStatus, UploadStatus
from app.repositories import file_chunk_repository as chunk_repo
from app.services.files import file_service
from app.services.files.file_retrieval_service import file_retrieval_service
from app.services.files.storage.local_provider import LocalFileStorage


@pytest.fixture
def storage(tmp_path) -> LocalFileStorage:
    return LocalFileStorage(str(tmp_path / "files"))


async def test_upload_text_processes_and_chunks(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    storage: LocalFileStorage,
) -> None:
    body = ("knowledge " * 400).encode("utf-8")
    file = await file_service.upload_file(
        db_session,
        user_id=seed_user,
        original_filename="notes.txt",
        content_type="text/plain",
        data=body,
        storage=storage,
    )
    assert file.upload_status == UploadStatus.UPLOADED
    assert file.processing_status == ProcessingStatus.COMPLETED
    assert file.chunk_count > 0
    assert file.error_message is None

    items, total = await chunk_repo.list_for_file(
        db_session, file_id=file.id, user_id=seed_user, limit=100, offset=0
    )
    assert total == file.chunk_count
    # The stored bytes are loadable through the storage backend.
    loaded = await storage.load(key=file.storage_path)
    assert loaded == body


async def test_upload_empty_file_rejected(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    storage: LocalFileStorage,
) -> None:
    with pytest.raises(file_service.EmptyFileError):
        await file_service.upload_file(
            db_session,
            user_id=seed_user,
            original_filename="empty.txt",
            content_type="text/plain",
            data=b"",
            storage=storage,
        )


async def test_upload_unsupported_type_rejected(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    storage: LocalFileStorage,
) -> None:
    from app.services.files.extraction_service import (
        UnsupportedFileTypeError,
    )

    with pytest.raises(UnsupportedFileTypeError):
        await file_service.upload_file(
            db_session,
            user_id=seed_user,
            original_filename="photo.png",
            content_type="image/png",
            data=b"\x89PNG\r\n",
            storage=storage,
        )


async def test_md_via_octet_stream_uses_extension(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    storage: LocalFileStorage,
) -> None:
    file = await file_service.upload_file(
        db_session,
        user_id=seed_user,
        original_filename="readme.md",
        content_type="application/octet-stream",
        data=b"# Heading\n\ntext",
        storage=storage,
    )
    assert file.mime_type == "text/markdown"
    assert file.processing_status == ProcessingStatus.COMPLETED


async def test_corrupt_pdf_marked_failed_not_raised(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    storage: LocalFileStorage,
) -> None:
    pytest.importorskip("pypdf")
    file = await file_service.upload_file(
        db_session,
        user_id=seed_user,
        original_filename="broken.pdf",
        content_type="application/pdf",
        data=b"%PDF-1.4 totally broken",
        storage=storage,
    )
    # Upload (bytes) succeeded; processing failed and was recorded.
    assert file.upload_status == UploadStatus.UPLOADED
    assert file.processing_status == ProcessingStatus.FAILED
    assert file.error_message
    assert file.chunk_count == 0


async def test_delete_removes_file_and_bytes(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    storage: LocalFileStorage,
) -> None:
    file = await file_service.upload_file(
        db_session,
        user_id=seed_user,
        original_filename="bye.txt",
        content_type="text/plain",
        data=b"goodbye",
        storage=storage,
    )
    key = file.storage_path
    await file_service.delete_file(
        db_session, user_id=seed_user, file_id=file.id, storage=storage
    )
    with pytest.raises(file_service.FileNotFoundError):
        await file_service.get_file(db_session, user_id=seed_user, file_id=file.id)
    # Bytes are gone from storage too.
    with pytest.raises(FileNotFoundError):
        await storage.load(key=key)


async def test_retrieval_service_search_scoped_to_tenant(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    storage: LocalFileStorage,
) -> None:
    file = await file_service.upload_file(
        db_session,
        user_id=seed_user,
        original_filename="cv.txt",
        content_type="text/plain",
        data=b"experienced compiler engineer",
        storage=storage,
    )
    hits = await file_retrieval_service.search_chunks(
        db_session, user_id=seed_user, query="compiler"
    )
    assert hits and any("compiler" in h.content for h in hits)
    # A foreign tenant sees nothing.
    none = await file_retrieval_service.search_chunks(
        db_session, user_id=uuid.uuid4(), query="compiler"
    )
    assert none == []
    # And cannot read the chunks of someone else's file (404).
    with pytest.raises(file_service.FileNotFoundError):
        await file_retrieval_service.get_chunks(
            db_session,
            user_id=uuid.uuid4(),
            file_id=file.id,
            limit=10,
            offset=0,
        )
