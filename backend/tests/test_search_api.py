"""API tests for the embed endpoint and search validation.

The embed endpoint runs end-to-end on SQLite (fake provider). Live semantic
ranking via ``POST /memories/search`` requires PostgreSQL + pgvector and is
verified against Supabase; here we cover its request validation.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import memory_embedding_repository as embed_repo


def _params(user_id: uuid.UUID, **extra: str | int) -> dict[str, str | int]:
    return {"user_id": str(user_id), **extra}


async def _create_memory(
    client: AsyncClient, user_id: uuid.UUID, content: str = "Applied to Qualcomm"
) -> str:
    resp = await client.post(
        "/api/v1/memories",
        params=_params(user_id),
        json={"category": "career", "content": content},
    )
    return str(resp.json()["id"])


async def test_embed_creates_and_is_idempotent(
    api_client: AsyncClient,
    db_session: AsyncSession,
    seed_user: uuid.UUID,
) -> None:
    memory_id = await _create_memory(api_client, seed_user)

    first = await api_client.post(
        f"/api/v1/memories/{memory_id}/embed", params=_params(seed_user)
    )
    assert first.status_code == 201
    body = first.json()
    assert body["memory_id"] == memory_id
    assert body["embedding_dimension"] == 384
    assert body["embedding_model"]
    content_hash = body["content_hash"]

    # Re-embedding unchanged content is idempotent (dedupe).
    second = await api_client.post(
        f"/api/v1/memories/{memory_id}/embed", params=_params(seed_user)
    )
    assert second.status_code == 201
    assert second.json()["content_hash"] == content_hash

    rows = await embed_repo.list_embeddings(db_session, memory_id=uuid.UUID(memory_id))
    assert len(rows) == 1


async def test_embed_unknown_memory_returns_404(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.post(
        f"/api/v1/memories/{uuid.uuid4()}/embed", params=_params(seed_user)
    )
    assert resp.status_code == 404


async def test_search_rejects_empty_query(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.post(
        "/api/v1/memories/search",
        params=_params(seed_user),
        json={"query": "   "},
    )
    assert resp.status_code == 422


async def test_search_requires_authentication(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/memories/search", json={"query": "companies I applied to"}
    )
    assert resp.status_code == 401
