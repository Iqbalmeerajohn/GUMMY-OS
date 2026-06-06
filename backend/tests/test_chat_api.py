"""Chat API tests (SQLite; search monkeypatched, fake LLM via api_client)."""

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


async def test_chat_endpoint_returns_reply(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    await api_client.post(
        "/api/v1/memories",
        params=_params(seed_user),
        json={"category": "career", "content": "Targeting Qualcomm"},
    )

    resp = await api_client.post(
        "/api/v1/chat",
        params=_params(seed_user),
        json={"message": "What am I preparing for?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # The fake LLM provider (wired in conftest) returns this canned reply.
    assert body["reply"] == "You are preparing for Qualcomm."
    assert body["memories_used"] >= 1
    assert body["model"]


async def test_chat_rejects_empty_message(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.post(
        "/api/v1/chat",
        params=_params(seed_user),
        json={"message": "   "},
    )
    assert resp.status_code == 422


async def test_chat_requires_user_id(api_client: AsyncClient) -> None:
    resp = await api_client.post("/api/v1/chat", json={"message": "hi"})
    assert resp.status_code == 422
