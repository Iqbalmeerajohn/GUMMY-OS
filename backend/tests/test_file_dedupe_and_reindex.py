"""Duplicate uploads and the repair path, through the real service.

Both exist for the same reason: a document store the user cannot correct is one
they stop trusting. Re-uploading the same file should not quietly produce a
second copy that splits search results, and a file that failed to index should
be fixable without the user hunting down the original.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import file_repository as file_repo
from app.services.files import file_service

CONTENT = b"Rajesh Kumar. CGPA 9.12. Backend engineer at Zerodha."


async def _upload(
    session: AsyncSession, user_id: uuid.UUID, name: str, data: bytes = CONTENT
):
    file = await file_service.upload_file(
        session,
        user_id=user_id,
        original_filename=name,
        content_type="text/plain",
        data=data,
    )
    await session.commit()
    return file


async def test_identical_bytes_return_the_existing_file(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    first = await _upload(db_session, seed_user, "resume.txt")
    second = await _upload(db_session, seed_user, "resume-final.txt")
    assert second.id == first.id


async def test_a_duplicate_upload_does_not_add_a_second_file(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Two copies would split search results across both."""
    await _upload(db_session, seed_user, "a.txt")
    await _upload(db_session, seed_user, "b.txt")
    _, total = await file_repo.list_files(
        db_session, user_id=seed_user, limit=50, offset=0
    )
    assert total == 1


async def test_different_content_is_not_deduplicated(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    first = await _upload(db_session, seed_user, "a.txt", b"first document content")
    second = await _upload(db_session, seed_user, "b.txt", b"second document content")
    assert first.id != second.id


async def test_deduplication_is_scoped_to_one_user(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Two people owning the same document is normal.

    A global checksum would collapse them, and worse, would tell one user that
    the other already holds that file.
    """
    mine = await _upload(db_session, seed_user, "shared.txt")
    theirs = await _upload(db_session, uuid.uuid4(), "shared.txt")
    assert mine.id != theirs.id


async def test_upload_marks_the_file_searchable(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    file = await _upload(db_session, seed_user, "notes.txt")
    assert file.indexed_at is not None
    assert file.chunk_count > 0


async def test_reindex_restores_a_file_that_lost_its_index(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """The path back for documents uploaded before embeddings existed."""
    file = await _upload(db_session, seed_user, "notes.txt")
    file.indexed_at = None
    await db_session.commit()

    repaired = await file_service.reindex_file(
        db_session, user_id=seed_user, file_id=file.id
    )
    await db_session.commit()
    assert repaired.indexed_at is not None
    assert repaired.chunk_count > 0


async def test_reindex_does_not_accumulate_chunks(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Chunking is deterministic, so a repair must replace, not append."""
    file = await _upload(db_session, seed_user, "notes.txt")
    before = file.chunk_count
    await file_service.reindex_file(db_session, user_id=seed_user, file_id=file.id)
    await db_session.commit()
    after = await file_repo.get_file(db_session, user_id=seed_user, file_id=file.id)
    assert after is not None
    assert after.chunk_count == before
