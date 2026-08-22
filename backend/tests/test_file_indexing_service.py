"""Embedding a file's chunks — the step that makes a document searchable.

The failure mode this guards is quiet: a file marked completed but never
embedded is invisible to every search, and the user discovers it by asking a
question and being told nothing was found, which looks identical to having
uploaded nothing.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProcessingStatus, UploadStatus
from app.models.file_chunk import FileChunk
from app.repositories import file_chunk_repository as chunk_repo
from app.repositories import file_repository as file_repo
from app.services.embeddings.factory import get_embedding_service
from app.services.files import indexing_service


async def _file_with_chunks(
    session: AsyncSession, user_id: uuid.UUID, count: int = 3
) -> uuid.UUID:
    file = await file_repo.create_file(
        session,
        user_id=user_id,
        filename="doc.txt",
        original_filename="doc.txt",
        mime_type="text/plain",
        size_bytes=10,
        storage_path=f"{user_id}/doc.txt",
        upload_status=UploadStatus.UPLOADED,
        processing_status=ProcessingStatus.COMPLETED,
    )
    await chunk_repo.bulk_create_chunks(
        session,
        user_id=user_id,
        file_id=file.id,
        chunks=[
            {"chunk_index": i, "content": f"chunk number {i}", "token_count": 4}
            for i in range(count)
        ],
    )
    await session.commit()
    return file.id


async def _chunks(session: AsyncSession, file_id: uuid.UUID) -> list[FileChunk]:
    stmt = select(FileChunk).where(FileChunk.file_id == file_id)
    return list((await session.execute(stmt)).scalars().all())


async def test_every_chunk_is_embedded(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    file_id = await _file_with_chunks(db_session, seed_user)
    embedded = await indexing_service.embed_file_chunks(
        db_session, user_id=seed_user, file_id=file_id
    )
    await db_session.commit()
    assert embedded == 3
    assert all(c.embedding is not None for c in await _chunks(db_session, file_id))


async def test_the_model_used_is_recorded_on_each_chunk(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Without it, a model change cannot tell stale vectors from fresh ones."""
    file_id = await _file_with_chunks(db_session, seed_user, count=1)
    await indexing_service.embed_file_chunks(
        db_session, user_id=seed_user, file_id=file_id
    )
    await db_session.commit()
    expected = get_embedding_service().model_name
    assert (await _chunks(db_session, file_id))[0].embedding_model == expected


async def test_embedding_failure_propagates(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """The caller marks the file failed, so this must not swallow the error.

    Catching it here would produce a file that looks ready and can never be
    found — the worst of both outcomes.
    """
    file_id = await _file_with_chunks(db_session, seed_user, count=1)

    class _Broken:
        model_name = "broken"

        async def embed_query(self, text: str) -> list[float]:
            raise RuntimeError("provider down")

    with pytest.raises(RuntimeError):
        await indexing_service.embed_file_chunks(
            db_session,
            user_id=seed_user,
            file_id=file_id,
            embedding_service=_Broken(),  # type: ignore[arg-type]
        )


async def test_re_embedding_overwrites_rather_than_accumulating(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Re-indexing must be idempotent, or chunks multiply on every repair."""
    file_id = await _file_with_chunks(db_session, seed_user)
    await indexing_service.embed_file_chunks(
        db_session, user_id=seed_user, file_id=file_id
    )
    await indexing_service.embed_file_chunks(
        db_session, user_id=seed_user, file_id=file_id
    )
    await db_session.commit()
    assert len(await _chunks(db_session, file_id)) == 3


async def test_a_file_with_no_chunks_embeds_nothing(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    assert (
        await indexing_service.embed_file_chunks(
            db_session, user_id=seed_user, file_id=uuid.uuid4()
        )
        == 0
    )


async def test_another_tenants_chunks_are_not_embedded(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Tenant scoping lives in the query: this runs on a shared session."""
    file_id = await _file_with_chunks(db_session, seed_user)
    embedded = await indexing_service.embed_file_chunks(
        db_session, user_id=uuid.uuid4(), file_id=file_id
    )
    assert embedded == 0
