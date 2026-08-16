"""Memory diagnostics endpoint tests (Req 7).

The pgvector candidate fetch is monkeypatched (SQLite), so the endpoint's
retrieval → ranking → prompt-selection trace is exercised end-to-end over HTTP.
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
    return [(memory, 0.1 * index) for index, memory in enumerate(items)]


async def test_diagnostics_traces_a_fact_to_the_prompt(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await api_client.post(
        "/api/v1/memories",
        params=_params(seed_user),
        json={"category": "profile", "content": "Birthday is July 1st"},
    )

    resp = await api_client.get(
        "/api/v1/memories/diagnostics",
        params=_params(seed_user, q="When is my birthday?"),
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_memories"] == 1
    assert body["retrieved_count"] == 1
    assert body["included_count"] == 1
    assert body["results"][0]["content"] == "Birthday is July 1st"
    assert body["results"][0]["included_in_prompt"] is True
    assert 0.0 <= body["results"][0]["final_score"] <= 1.0
    assert "July 1st" in body["prompt_memory_block"]
    # Extraction visibility: the flag is consistent with the reported mode.
    assert body["extraction_enabled"] == (body["consent_mode"] == "autonomous")


async def test_diagnostics_with_no_memories(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    resp = await api_client.get(
        "/api/v1/memories/diagnostics",
        params=_params(seed_user, q="When is my birthday?"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_memories"] == 0
    assert body["retrieved_count"] == 0
    assert body["included_count"] == 0
    assert body["prompt_memory_block"] == "(no memories selected)"


async def test_diagnostics_requires_query(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
) -> None:
    resp = await api_client.get(
        "/api/v1/memories/diagnostics", params=_params(seed_user)
    )
    assert resp.status_code == 422
