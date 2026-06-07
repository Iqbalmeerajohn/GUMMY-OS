"""Retrieval API tests.

The pgvector candidate fetch is monkeypatched (SQLite can't run ``<=>``), so the
hybrid ranking + reinforcement orchestration is exercised end-to-end over HTTP.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory
from app.models.memory import Memory
from app.repositories import memory_repository as repo


def _params(user_id: uuid.UUID, **extra: str | int) -> dict[str, str | int]:
    return {"user_id": str(user_id), **extra}


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
    # Assign increasing cosine distances so order is deterministic.
    return [(memory, 0.1 * index) for index, memory in enumerate(items)]


async def _create_memory(client: AsyncClient, user_id: uuid.UUID, content: str) -> None:
    await client.post(
        "/api/v1/memories",
        params=_params(user_id),
        json={"category": "career", "content": content},
    )


async def test_retrieve_returns_ranked_and_reinforces(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    for content in ("Applied to Qualcomm", "Applied to NVIDIA", "Likes tea"):
        await _create_memory(api_client, seed_user, content)

    resp = await api_client.post(
        "/api/v1/memories/retrieve",
        params=_params(seed_user),
        json={"query": "companies I applied to"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 3

    scores = [r["final_score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)  # ranked best-first
    for result in body["results"]:
        assert 0.0 <= result["final_score"] <= 1.0
        assert result["recall_count"] == 1  # reinforced once


async def test_retrieve_without_reinforcement(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    await _create_memory(api_client, seed_user, "Applied to Qualcomm")

    resp = await api_client.post(
        "/api/v1/memories/retrieve",
        params=_params(seed_user),
        json={"query": "qualcomm", "reinforce": False},
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["recall_count"] == 0


async def test_retrieve_rejects_empty_query(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.post(
        "/api/v1/memories/retrieve",
        params=_params(seed_user),
        json={"query": "   "},
    )
    assert resp.status_code == 422


async def test_retrieve_requires_authentication(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/memories/retrieve", json={"query": "anything"}
    )
    assert resp.status_code == 401
