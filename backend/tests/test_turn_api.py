"""API tests for the turn endpoint (M4): POST /conversations/{id}/messages.

SQLite; pgvector search monkeypatched. The api_client fixture wires the fake LLM
(canned reply) and fake embeddings.
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


async def _new_conversation(client: AsyncClient, user_id: uuid.UUID) -> str:
    resp = await client.post(
        "/api/v1/conversations", params=_params(user_id), json={}
    )
    return resp.json()["id"]


async def test_turn_returns_201_and_persists(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    conv_id = await _new_conversation(api_client, seed_user)

    resp = await api_client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        params=_params(seed_user),
        json={"message": "What am I preparing for?"},
    )
    assert resp.status_code == 201
    body = resp.json()
    # Canned reply from the fake LLM wired in conftest.
    assert body["reply"] == "You are preparing for Qualcomm."
    assert body["conversation_id"] == conv_id
    assert body["message_count"] == 2
    assert uuid.UUID(body["user_message_id"])
    assert uuid.UUID(body["assistant_message_id"])
    assert body["model"]

    # History now reflects both persisted turns, oldest first.
    history = await api_client.get(
        f"/api/v1/conversations/{conv_id}/messages", params=_params(seed_user)
    )
    items = history.json()["items"]
    assert [m["role"] for m in items] == ["user", "assistant"]
    assert items[0]["content"] == "What am I preparing for?"
    assert items[1]["content"] == "You are preparing for Qualcomm."


async def test_turn_stream_emits_sse_and_persists(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    conv_id = await _new_conversation(api_client, seed_user)

    resp = await api_client.post(
        f"/api/v1/conversations/{conv_id}/messages/stream",
        params=_params(seed_user),
        json={"message": "What am I preparing for?"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    body = resp.text
    # Fake LLM has no streaming → fallback emits the full reply as one delta.
    assert "You are preparing for Qualcomm." in body
    assert '"type": "delta"' in body
    assert '"type": "done"' in body

    # Both turns were persisted once the stream finished.
    history = await api_client.get(
        f"/api/v1/conversations/{conv_id}/messages", params=_params(seed_user)
    )
    items = history.json()["items"]
    assert [m["role"] for m in items] == ["user", "assistant"]
    assert items[1]["content"] == "You are preparing for Qualcomm."


async def test_turn_bumps_conversation_counter(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    conv_id = await _new_conversation(api_client, seed_user)
    for _ in range(2):
        await api_client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            params=_params(seed_user),
            json={"message": "hi"},
        )
    detail = await api_client.get(
        f"/api/v1/conversations/{conv_id}", params=_params(seed_user)
    )
    body = detail.json()
    assert body["message_count"] == 4
    assert body["last_message_at"] is not None


async def test_turn_rejects_empty_message(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
) -> None:
    conv_id = await _new_conversation(api_client, seed_user)
    resp = await api_client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        params=_params(seed_user),
        json={"message": "   "},
    )
    assert resp.status_code == 422


async def test_turn_unknown_conversation_404(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    resp = await api_client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        params=_params(seed_user),
        json={"message": "hi"},
    )
    assert resp.status_code == 404


async def test_turn_requires_authentication(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={"message": "hi"},
    )
    assert resp.status_code == 401


async def test_turn_is_tenant_isolated(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    conv_id = await _new_conversation(api_client, seed_user)
    # A different tenant cannot post a turn into this conversation.
    resp = await api_client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        params=_params(uuid.uuid4()),
        json={"message": "intrude"},
    )
    assert resp.status_code == 404
