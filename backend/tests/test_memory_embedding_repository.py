"""Repository tests for memory embeddings (SQLite, JSON-variant vector)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory
from app.repositories import memory_embedding_repository as embed_repo
from app.repositories import memory_repository as repo

_MODEL = "fake-deterministic-v1"


async def _memory_id(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    memory = await repo.create_memory(
        session,
        user_id=user_id,
        category=MemoryCategory.PROFILE,
        content="hello",
        importance_score=0.5,
        confidence_score=0.5,
    )
    await session.commit()
    return memory.id


async def test_get_returns_none_when_absent(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory_id = await _memory_id(db_session, seed_user)
    got = await embed_repo.get_embedding(
        db_session, memory_id=memory_id, embedding_model=_MODEL
    )
    assert got is None


async def test_create_and_get(db_session: AsyncSession, seed_user: uuid.UUID) -> None:
    memory_id = await _memory_id(db_session, seed_user)
    created = await embed_repo.create_embedding(
        db_session,
        user_id=seed_user,
        memory_id=memory_id,
        embedding_model=_MODEL,
        embedding_dimension=384,
        content_hash="hash-1",
        embedding_vector=[0.1] * 384,
    )
    await db_session.commit()

    got = await embed_repo.get_embedding(
        db_session, memory_id=memory_id, embedding_model=_MODEL
    )
    assert got is not None
    assert got.id == created.id
    assert got.embedding_dimension == 384
    assert len(got.embedding_vector) == 384


async def test_update_overwrites_vector_and_hash(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory_id = await _memory_id(db_session, seed_user)
    created = await embed_repo.create_embedding(
        db_session,
        user_id=seed_user,
        memory_id=memory_id,
        embedding_model=_MODEL,
        embedding_dimension=384,
        content_hash="hash-1",
        embedding_vector=[0.1] * 384,
    )
    await db_session.commit()

    await embed_repo.update_embedding(
        db_session,
        created,
        embedding_vector=[0.2] * 384,
        content_hash="hash-2",
        embedding_dimension=384,
    )
    await db_session.commit()

    got = await embed_repo.get_embedding(
        db_session, memory_id=memory_id, embedding_model=_MODEL
    )
    assert got is not None
    assert got.content_hash == "hash-2"
    assert got.embedding_vector[0] == 0.2


async def test_list_embeddings(db_session: AsyncSession, seed_user: uuid.UUID) -> None:
    memory_id = await _memory_id(db_session, seed_user)
    assert await embed_repo.list_embeddings(db_session, memory_id=memory_id) == []
    await embed_repo.create_embedding(
        db_session,
        user_id=seed_user,
        memory_id=memory_id,
        embedding_model=_MODEL,
        embedding_dimension=384,
        content_hash="hash-1",
        embedding_vector=[0.0] * 384,
    )
    await db_session.commit()
    rows = await embed_repo.list_embeddings(db_session, memory_id=memory_id)
    assert len(rows) == 1
