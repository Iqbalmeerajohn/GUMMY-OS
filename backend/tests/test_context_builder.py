"""Context Builder tests (Phase 3, M4)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory
from app.models.memory import Memory
from app.repositories import memory_repository as mem_repo
from app.services.agents import context_builder
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider


async def _fake_search(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query_vector: list[float],
    embedding_model: str,
    limit: int,
    include_archived: bool = False,
    category: MemoryCategory | None = None,
) -> list[tuple[Memory, float]]:
    items, _ = await mem_repo.list_memories(
        session, user_id=user_id, limit=limit, offset=0
    )
    return [(memory, 0.9 - 0.1 * index) for index, memory in enumerate(items)]


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


async def _seed_memories(
    session: AsyncSession, user_id: uuid.UUID, count: int
) -> None:
    for index in range(count):
        await mem_repo.create_memory(
            session,
            user_id=user_id,
            category=MemoryCategory.CAREER,
            content=f"fact number {index}",
            importance_score=0.5,
            confidence_score=0.5,
        )
    await session.commit()


async def test_pack_contains_ranked_memories_and_thread_context(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    await _seed_memories(db_session, seed_user, 3)
    history = [{"role": "user", "content": "earlier message"}]
    pack = await context_builder.build(
        db_session,
        user_id=seed_user,
        query="what do you know?",
        embedding_service=_embeddings(),
        history=history,
        summary="prior summary",
    )
    assert len(pack.memories) == 3
    first = pack.memories[0]
    assert set(first) == {"content", "category", "score"}
    assert first["category"] == "career"
    assert pack.history == history
    assert pack.summary == "prior summary"
    assert pack.goals == []
    assert pack.tasks == []
    assert pack.scratch == []


async def test_pack_defaults_when_no_context(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    pack = await context_builder.build(
        db_session,
        user_id=seed_user,
        query="hello",
        embedding_service=_embeddings(),
    )
    assert pack.memories == []
    assert pack.history == []
    assert pack.summary is None


async def test_max_memories_caps_candidates(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    await _seed_memories(db_session, seed_user, 6)
    pack = await context_builder.build(
        db_session,
        user_id=seed_user,
        query="facts",
        embedding_service=_embeddings(),
        max_memories=2,
    )
    assert len(pack.memories) == 2
