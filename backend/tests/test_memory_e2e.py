"""End-to-end memory tests (M4 completion gate).

Exercises the full memory lifecycle through the real HTTP API — the same
endpoints the Memory Center and chat use: save, retrieve (hybrid), cross-
conversation recall (a fact saved outside a thread is used inside a new one),
semantic search, and delete.

SQLite; pgvector candidate fetch is monkeypatched (Postgres-only), and the
api_client fixture wires the fake LLM + fake embeddings.
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
    items, _ = await repo.list_memories(
        session, user_id=user_id, limit=limit, offset=0
    )
    return [(memory, 0.1 * index) for index, memory in enumerate(items)]


async def test_memory_lifecycle_end_to_end(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )

    # 1. SAVE — create a memory via the API.
    created = await api_client.post(
        "/api/v1/memories",
        params=_params(seed_user),
        json={
            "category": "preference",
            "content": "Favorite football player is Cristiano Ronaldo",
        },
    )
    assert created.status_code == 201
    mem_id = created.json()["id"]

    # 2. RETRIEVE — hybrid retrieval surfaces the saved fact.
    retrieved = await api_client.post(
        "/api/v1/memories/retrieve",
        params=_params(seed_user),
        json={"query": "favorite football player", "limit": 5},
    )
    assert retrieved.status_code == 200
    assert any(
        "Ronaldo" in r["content"] for r in retrieved.json()["results"]
    )

    # 3. CROSS-CONVERSATION RECALL — a brand-new conversation uses the memory
    #    that was saved entirely outside it.
    conv = await api_client.post(
        "/api/v1/conversations", params=_params(seed_user), json={}
    )
    conv_id = conv.json()["id"]
    turn = await api_client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        params=_params(seed_user),
        json={"message": "Who is my favorite football player?"},
    )
    assert turn.status_code == 201
    assert turn.json()["memories_used"] >= 1

    # 4. SEARCH — semantic search returns the memory.
    searched = await api_client.post(
        "/api/v1/memories/search",
        params=_params(seed_user),
        json={"query": "football", "limit": 5},
    )
    assert searched.status_code == 200
    assert any("Ronaldo" in r["content"] for r in searched.json()["results"])

    # 5. DELETE — soft-delete removes it from the list.
    deleted = await api_client.delete(
        f"/api/v1/memories/{mem_id}", params=_params(seed_user)
    )
    assert deleted.status_code == 204
    listing = await api_client.get(
        "/api/v1/memories", params=_params(seed_user)
    )
    assert all(m["id"] != mem_id for m in listing.json()["items"])


async def test_archive_then_restore_round_trip(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
) -> None:
    created = await api_client.post(
        "/api/v1/memories",
        params=_params(seed_user),
        json={"category": "profile", "content": "Based in Kuala Lumpur"},
    )
    mem_id = created.json()["id"]

    archived = await api_client.post(
        f"/api/v1/memories/{mem_id}/archive", params=_params(seed_user)
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    restored = await api_client.post(
        f"/api/v1/memories/{mem_id}/restore", params=_params(seed_user)
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"
