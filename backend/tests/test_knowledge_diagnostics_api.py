"""Knowledge diagnostics endpoint tests (M7) — ``GET /knowledge/diagnostics``.

Proves the endpoint traces a query through retrieval → ranking → compression and
reports per-source counts, the fused ranking, and the prompt ``<knowledge>``
block, without mutating memory scores (read-only).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory
from app.models.memory import Memory
from app.repositories import goal_repository
from app.repositories import memory_repository as mem_repo


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
    return [(memory, 0.1 * index) for index, memory in enumerate(items)]


async def _seed(session: AsyncSession, user_id: uuid.UUID) -> None:
    await mem_repo.create_memory(
        session,
        user_id=user_id,
        category=MemoryCategory.CAREER,
        content="Preparing for an AI Engineer interview",
        importance_score=0.9,
        confidence_score=0.9,
    )
    await goal_repository.create_goal(
        session, user_id=user_id, title="Land an AI Engineer job"
    )
    await session.commit()


async def test_diagnostics_traces_all_sources(
    api_client: AsyncClient,
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _seed(db_session, seed_user)

    resp = await api_client.get(
        "/api/v1/knowledge/diagnostics",
        params={"user_id": str(seed_user), "q": "AI Engineer"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "AI Engineer"
    assert body["memories_used"] >= 1
    assert body["goals_used"] >= 1
    assert "memory" in body["sources_used"]
    assert "goal" in body["sources_used"]
    assert body["ranked_items"], "expected ranked items"
    # Every item keeps provenance + a prompt-inclusion verdict.
    for item in body["ranked_items"]:
        assert item["source"] in {"memory", "goal", "file"}
        assert "included_in_prompt" in item
    assert "<" not in body["knowledge_block"] or "[memory" in body["knowledge_block"]
    assert body["token_estimate"] > 0


async def test_diagnostics_rejects_blank_query(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
) -> None:
    resp = await api_client.get(
        "/api/v1/knowledge/diagnostics",
        params={"user_id": str(seed_user), "q": "   "},
    )
    assert resp.status_code == 422


async def test_diagnostics_is_read_only(
    api_client: AsyncClient,
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reinforcement is disabled, so recall_count must not change."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _seed(db_session, seed_user)
    before, _ = await mem_repo.list_memories(
        db_session, user_id=seed_user, limit=10, offset=0
    )
    before_counts = {m.id: m.recall_count for m in before}

    resp = await api_client.get(
        "/api/v1/knowledge/diagnostics",
        params={"user_id": str(seed_user), "q": "AI Engineer"},
    )
    assert resp.status_code == 200

    after, _ = await mem_repo.list_memories(
        db_session, user_id=seed_user, limit=10, offset=0
    )
    for m in after:
        assert m.recall_count == before_counts[m.id]
