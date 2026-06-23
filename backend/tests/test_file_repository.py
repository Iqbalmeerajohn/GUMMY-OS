"""Repository tests for files + file chunks (M6): persistence + tenancy."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProcessingStatus, UploadStatus
from app.repositories import file_chunk_repository as chunk_repo
from app.repositories import file_repository as repo


async def _make_file(
    session: AsyncSession,
    user_id: uuid.UUID,
    name: str = "doc.txt",
) -> uuid.UUID:
    file = await repo.create_file(
        session,
        user_id=user_id,
        filename=name,
        original_filename=name,
        mime_type="text/plain",
        size_bytes=10,
        storage_path=f"{user_id}/{name}",
        upload_status=UploadStatus.UPLOADED,
        processing_status=ProcessingStatus.COMPLETED,
    )
    await session.commit()
    return file.id


async def test_create_and_get_file(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    file_id = await _make_file(db_session, seed_user)
    fetched = await repo.get_file(db_session, file_id=file_id, user_id=seed_user)
    assert fetched is not None
    assert fetched.original_filename == "doc.txt"
    assert fetched.upload_status == UploadStatus.UPLOADED


async def test_get_file_other_tenant_returns_none(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    file_id = await _make_file(db_session, seed_user)
    other = await repo.get_file(db_session, file_id=file_id, user_id=uuid.uuid4())
    assert other is None


async def test_list_files_newest_first_and_total(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    await _make_file(db_session, seed_user, "a.txt")
    await _make_file(db_session, seed_user, "b.txt")
    await _make_file(db_session, seed_user, "c.txt")
    items, total = await repo.list_files(
        db_session, user_id=seed_user, limit=10, offset=0
    )
    assert total == 3
    assert [f.original_filename for f in items] == ["c.txt", "b.txt", "a.txt"]


async def test_count_and_recent(db_session: AsyncSession, seed_user: uuid.UUID) -> None:
    for i in range(5):
        await _make_file(db_session, seed_user, f"f{i}.txt")
    assert await repo.count_files(db_session, user_id=seed_user) == 5
    recent = await repo.list_recent(db_session, user_id=seed_user, limit=2)
    assert len(recent) == 2


async def test_bulk_create_and_list_chunks(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    file_id = await _make_file(db_session, seed_user)
    created = await chunk_repo.bulk_create_chunks(
        db_session,
        user_id=seed_user,
        file_id=file_id,
        chunks=[
            {"chunk_index": 0, "content": "alpha", "token_count": 1},
            {"chunk_index": 1, "content": "beta", "token_count": 1},
        ],
    )
    await db_session.commit()
    assert created == 2
    items, total = await chunk_repo.list_for_file(
        db_session, file_id=file_id, user_id=seed_user, limit=10, offset=0
    )
    assert total == 2
    assert [c.chunk_index for c in items] == [0, 1]


async def test_search_chunks_keyword(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    file_id = await _make_file(db_session, seed_user)
    await chunk_repo.bulk_create_chunks(
        db_session,
        user_id=seed_user,
        file_id=file_id,
        chunks=[
            {"chunk_index": 0, "content": "compiler design notes", "token_count": 3},
            {"chunk_index": 1, "content": "unrelated content", "token_count": 2},
        ],
    )
    await db_session.commit()
    hits = await chunk_repo.search_chunks(
        db_session, user_id=seed_user, query="compiler", limit=10
    )
    assert len(hits) == 1
    assert "compiler" in hits[0].content


async def test_delete_for_file_removes_chunks(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    file_id = await _make_file(db_session, seed_user)
    await chunk_repo.bulk_create_chunks(
        db_session,
        user_id=seed_user,
        file_id=file_id,
        chunks=[{"chunk_index": 0, "content": "x", "token_count": 1}],
    )
    await db_session.commit()
    await chunk_repo.delete_for_file(db_session, file_id=file_id, user_id=seed_user)
    await db_session.commit()
    _, total = await chunk_repo.list_for_file(
        db_session, file_id=file_id, user_id=seed_user, limit=10, offset=0
    )
    assert total == 0
