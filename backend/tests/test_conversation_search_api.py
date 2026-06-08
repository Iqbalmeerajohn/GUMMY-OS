"""API tests for conversation search (M7).

FTS/pgvector are PostgreSQL-only, so the repo searches are monkeypatched; this
covers routing, validation, auth, and response shape on SQLite.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


def _params(user_id: uuid.UUID, **extra: str | int) -> dict[str, str | int]:
    return {"user_id": str(user_id), **extra}


async def _new_conversation(client: AsyncClient, user_id: uuid.UUID) -> str:
    resp = await client.post(
        "/api/v1/conversations",
        params=_params(user_id),
        json={"title": "RTOS scheduling chat"},
    )
    return resp.json()["id"]


async def test_search_returns_ranked_results(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conv_id = await _new_conversation(api_client, seed_user)
    match_msg = uuid.uuid4()

    async def _kw(session, *, user_id, query, limit):  # noqa: ANN001, ANN202
        return [(uuid.UUID(conv_id), match_msg, 1.0)]

    monkeypatch.setattr(
        "app.repositories.conversation_search_repository.keyword_search", _kw
    )

    resp = await api_client.get(
        "/api/v1/conversations/search",
        params=_params(seed_user, q="rtos", mode="keyword"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "rtos"
    assert body["mode"] == "keyword"
    assert body["count"] == 1
    result = body["results"][0]
    assert result["conversation_id"] == conv_id
    assert result["title"] == "RTOS scheduling chat"
    assert result["score"] == 1.0
    assert result["match_message_id"] == str(match_msg)


async def test_search_defaults_to_hybrid_mode(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _empty(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        return []

    monkeypatch.setattr(
        "app.repositories.conversation_search_repository.keyword_search", _empty
    )
    monkeypatch.setattr(
        "app.repositories.conversation_search_repository.summary_semantic_search",
        _empty,
    )
    resp = await api_client.get(
        "/api/v1/conversations/search", params=_params(seed_user, q="anything")
    )
    assert resp.status_code == 200
    assert resp.json()["mode"] == "hybrid"


async def test_search_rejects_blank_query(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.get(
        "/api/v1/conversations/search", params=_params(seed_user, q="   ")
    )
    assert resp.status_code == 422


async def test_search_rejects_invalid_mode(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.get(
        "/api/v1/conversations/search",
        params=_params(seed_user, q="x", mode="fuzzy"),
    )
    assert resp.status_code == 422


async def test_search_requires_authentication(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/v1/conversations/search", params={"q": "x"})
    assert resp.status_code == 401


async def test_search_route_not_shadowed_by_get_by_id(
    api_client: AsyncClient,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # "/conversations/search" must hit the search route, not /{conversation_id}
    # (which would 422 trying to parse "search" as a UUID).
    async def _empty(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        return []

    monkeypatch.setattr(
        "app.repositories.conversation_search_repository.keyword_search", _empty
    )
    monkeypatch.setattr(
        "app.repositories.conversation_search_repository.summary_semantic_search",
        _empty,
    )
    resp = await api_client.get(
        "/api/v1/conversations/search",
        params=_params(seed_user, q="x", mode="keyword"),
    )
    assert resp.status_code == 200
