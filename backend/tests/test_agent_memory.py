"""Shared Agent Memory facade tests (Phase 3, M7).

Proves: ``recall`` is pure delegation to hybrid retrieval; ``propose``
persists only under ``autonomous`` consent, routes through the Memory Engine
(default scores, versioning, embedding enqueue), records
``source_kind='agent'`` provenance, validates/caps candidates, and rejects
invalid categories. The widened SourceKind CHECK accepts ``agent``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    DEFAULT_CONFIDENCE_SCORE,
    DEFAULT_IMPORTANCE_SCORE,
    EXTRACTION_MAX_MEMORIES,
)
from app.models.enums import ConsentMode, MemoryCategory, SourceKind
from app.models.memory import Memory
from app.models.memory_source import MemorySource
from app.models.memory_version import MemoryVersion
from app.repositories import memory_repository as mem_repo
from app.services.agents import agent_memory
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
    return [(memory, 0.8) for memory in items]


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


# ── recall ────────────────────────────────────────────────────────────────────


async def test_recall_delegates_to_hybrid_retrieval(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    await mem_repo.create_memory(
        db_session,
        user_id=seed_user,
        category=MemoryCategory.CAREER,
        content="Knows SystemVerilog",
        importance_score=0.7,
        confidence_score=0.7,
    )
    await db_session.commit()
    hits = await agent_memory.recall(
        db_session,
        user_id=seed_user,
        query="hardware skills",
        embedding_service=_embeddings(),
        limit=5,
    )
    assert len(hits) == 1
    assert hits[0].memory.content == "Knows SystemVerilog"
    assert 0.0 <= hits[0].final_score <= 1.0


# ── propose: consent gate ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "mode", [ConsentMode.ASSISTED, ConsentMode.EXPLICIT]
)
async def test_propose_persists_nothing_without_autonomous_consent(
    db_session: AsyncSession, seed_user: uuid.UUID, mode: ConsentMode
) -> None:
    created = await agent_memory.propose(
        db_session,
        user_id=seed_user,
        candidates=[{"content": "A durable fact", "category": "career"}],
        agent_key="recall",
        consent_mode=mode,
    )
    assert created == []
    memories = (await db_session.execute(select(Memory))).scalars().all()
    assert memories == []


async def test_propose_autonomous_writes_with_agent_provenance(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    created = await agent_memory.propose(
        db_session,
        user_id=seed_user,
        candidates=[
            {"content": "Prefers morning workouts", "category": "preference"}
        ],
        agent_key="recall",
        conversation_id=None,
        consent_mode=ConsentMode.AUTONOMOUS,
    )
    assert len(created) == 1
    memory = created[0]
    # Routed through the Memory Engine: default scores + version 1 snapshot.
    assert memory.importance_score == DEFAULT_IMPORTANCE_SCORE
    assert memory.confidence_score == DEFAULT_CONFIDENCE_SCORE
    versions = (
        (await db_session.execute(select(MemoryVersion))).scalars().all()
    )
    assert len(versions) == 1
    # Provenance: source_kind='agent' (the widened bus).
    sources = (
        (await db_session.execute(select(MemorySource))).scalars().all()
    )
    assert len(sources) == 1
    assert sources[0].source_kind == SourceKind.AGENT
    assert sources[0].memory_id == memory.id


async def test_propose_validates_and_caps_candidates(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    candidates: list[dict] = [
        {"content": "", "category": "career"},  # empty → skipped
        {"content": "ok fact", "category": "not-a-category"},  # skipped
        {"content": "no category"},  # skipped
        "not even a dict",  # type: ignore[list-item]
    ]
    candidates += [
        {"content": f"fact {i}", "category": "project"}
        for i in range(EXTRACTION_MAX_MEMORIES + 5)
    ]
    created = await agent_memory.propose(
        db_session,
        user_id=seed_user,
        candidates=candidates,
        agent_key="recall",
        consent_mode=ConsentMode.AUTONOMOUS,
    )
    assert len(created) == EXTRACTION_MAX_MEMORIES  # capped, invalid skipped
    assert all(m.category == MemoryCategory.PROJECT for m in created)


async def test_settings_consent_mode_respected(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings

    # The suite default is "assisted" → nothing persists without an override.
    monkeypatch.setattr(get_settings(), "memory_consent_mode", "assisted")
    created = await agent_memory.propose(
        db_session,
        user_id=seed_user,
        candidates=[{"content": "fact", "category": "career"}],
        agent_key="recall",
    )
    assert created == []
