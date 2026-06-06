"""Memory-aware chat service tests (SQLite; pgvector search monkeypatched)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory
from app.models.memory import Memory
from app.repositories import memory_repository as repo
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.llm.fake_provider import FakeLLMProvider
from app.services.memory import chat_service


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
    items, _ = await repo.list_memories(session, user_id=user_id, limit=limit, offset=0)
    return [(memory, 0.1 * index) for index, memory in enumerate(items)]


async def test_chat_grounds_reply_in_memory(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    await repo.create_memory(
        db_session,
        user_id=seed_user,
        category=MemoryCategory.CAREER,
        content="Targeting Qualcomm",
        importance_score=0.5,
        confidence_score=0.5,
    )
    await db_session.commit()

    llm = FakeLLMProvider(reply="You are preparing for Qualcomm.")
    result = await chat_service.chat(
        db_session,
        user_id=seed_user,
        message="What am I preparing for?",
        embedding_service=EmbeddingService(FakeEmbeddingProvider()),
        llm=llm,
    )

    assert result.reply == "You are preparing for Qualcomm."
    assert result.memories_used == 1
    assert result.model == "fake-model"
    # The memory was actually packed into the system prompt sent to the LLM.
    assert "Targeting Qualcomm" in str(llm.calls[0]["system"])


async def test_chat_with_no_memories(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    llm = FakeLLMProvider(reply="I don't have that yet.")
    result = await chat_service.chat(
        db_session,
        user_id=seed_user,
        message="What am I preparing for?",
        embedding_service=EmbeddingService(FakeEmbeddingProvider()),
        llm=llm,
    )
    assert result.memories_used == 0
    assert "No relevant memories" in str(llm.calls[0]["system"])
