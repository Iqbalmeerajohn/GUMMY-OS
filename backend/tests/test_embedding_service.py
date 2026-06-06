"""Embedding service tests: generation, hashing, dedupe, update-on-edit."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory
from app.models.memory import Memory
from app.repositories import memory_embedding_repository as embed_repo
from app.repositories import memory_repository as repo
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider


async def _make_memory(
    session: AsyncSession,
    user_id: uuid.UUID,
    content: str = "I applied to Qualcomm",
) -> Memory:
    memory = await repo.create_memory(
        session,
        user_id=user_id,
        category=MemoryCategory.CAREER,
        content=content,
        importance_score=0.5,
        confidence_score=0.5,
    )
    await session.commit()
    return memory


def test_fake_provider_is_deterministic_and_normalized() -> None:
    provider = FakeEmbeddingProvider()
    v1 = provider.embed_text("hello")
    v2 = provider.embed_text("hello")
    assert v1 == v2
    assert len(v1) == provider.dimension == 384
    norm = sum(x * x for x in v1) ** 0.5
    assert abs(norm - 1.0) < 1e-6


async def test_sync_creates_embedding(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory = await _make_memory(db_session, seed_user)
    provider = FakeEmbeddingProvider()
    service = EmbeddingService(provider)

    embedding = await service.sync_memory_embedding(db_session, memory=memory)
    await db_session.commit()

    assert embedding.embedding_model == provider.model_name
    assert embedding.embedding_dimension == 384
    assert len(embedding.embedding_vector) == 384
    assert embedding.content_hash == EmbeddingService.compute_content_hash(
        memory.content
    )


async def test_sync_dedupes_unchanged_content(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory = await _make_memory(db_session, seed_user)
    provider = FakeEmbeddingProvider()
    service = EmbeddingService(provider)

    await service.sync_memory_embedding(db_session, memory=memory)
    await db_session.commit()
    await service.sync_memory_embedding(db_session, memory=memory)
    await db_session.commit()

    assert provider.call_count == 1  # second sync skipped the recompute
    rows = await embed_repo.list_embeddings(db_session, memory_id=memory.id)
    assert len(rows) == 1


async def test_sync_updates_on_content_change(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory = await _make_memory(db_session, seed_user, content="targeting Qualcomm")
    provider = FakeEmbeddingProvider()
    service = EmbeddingService(provider)

    first = await service.sync_memory_embedding(db_session, memory=memory)
    await db_session.commit()
    first_hash = first.content_hash
    first_vector = list(first.embedding_vector)

    memory.content = "targeting NVIDIA"
    await db_session.flush()
    second = await service.sync_memory_embedding(db_session, memory=memory)
    await db_session.commit()

    assert provider.call_count == 2
    assert second.id == first.id  # updated in place, not duplicated
    assert second.content_hash != first_hash
    assert list(second.embedding_vector) != first_vector
    rows = await embed_repo.list_embeddings(db_session, memory_id=memory.id)
    assert len(rows) == 1
