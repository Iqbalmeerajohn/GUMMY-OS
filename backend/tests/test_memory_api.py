"""API-layer tests for the Memory CRUD endpoints."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


def _params(user_id: uuid.UUID, **extra: str | int) -> dict[str, str | int]:
    return {"user_id": str(user_id), **extra}


async def test_create_memory_returns_201(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.post(
        "/api/v1/memories",
        params=_params(seed_user),
        json={"category": "career", "content": "Targeting Qualcomm"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["category"] == "career"
    assert body["content"] == "Targeting Qualcomm"
    assert body["status"] == "active"
    assert body["importance_score"] == 0.5
    assert body["confidence_score"] == 0.5
    assert uuid.UUID(body["id"])


async def test_create_validation_error(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.post(
        "/api/v1/memories",
        params=_params(seed_user),
        json={"category": "career", "content": "   "},
    )
    assert resp.status_code == 422


async def test_list_memories(api_client: AsyncClient, seed_user: uuid.UUID) -> None:
    for text in ("a", "b"):
        await api_client.post(
            "/api/v1/memories",
            params=_params(seed_user),
            json={"category": "profile", "content": text},
        )
    resp = await api_client.get("/api/v1/memories", params=_params(seed_user, limit=10))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["limit"] == 10


async def test_get_memory_by_id_and_404(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    created = await api_client.post(
        "/api/v1/memories",
        params=_params(seed_user),
        json={"category": "profile", "content": "Bangalore"},
    )
    memory_id = created.json()["id"]

    ok = await api_client.get(
        f"/api/v1/memories/{memory_id}", params=_params(seed_user)
    )
    assert ok.status_code == 200
    assert ok.json()["content"] == "Bangalore"

    missing = await api_client.get(
        f"/api/v1/memories/{uuid.uuid4()}", params=_params(seed_user)
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "memory_not_found"


async def test_update_memory(api_client: AsyncClient, seed_user: uuid.UUID) -> None:
    created = await api_client.post(
        "/api/v1/memories",
        params=_params(seed_user),
        json={"category": "career", "content": "Qualcomm"},
    )
    memory_id = created.json()["id"]

    resp = await api_client.patch(
        f"/api/v1/memories/{memory_id}",
        params=_params(seed_user),
        json={"content": "NVIDIA", "importance_score": 0.9},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "NVIDIA"
    assert body["importance_score"] == 0.9


async def test_archive_memory(api_client: AsyncClient, seed_user: uuid.UUID) -> None:
    created = await api_client.post(
        "/api/v1/memories",
        params=_params(seed_user),
        json={"category": "career", "content": "Qualcomm"},
    )
    memory_id = created.json()["id"]

    resp = await api_client.post(
        f"/api/v1/memories/{memory_id}/archive", params=_params(seed_user)
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


async def test_delete_is_soft(api_client: AsyncClient, seed_user: uuid.UUID) -> None:
    created = await api_client.post(
        "/api/v1/memories",
        params=_params(seed_user),
        json={"category": "profile", "content": "temp"},
    )
    memory_id = created.json()["id"]

    deleted = await api_client.delete(
        f"/api/v1/memories/{memory_id}", params=_params(seed_user)
    )
    assert deleted.status_code == 204

    after = await api_client.get(
        f"/api/v1/memories/{memory_id}", params=_params(seed_user)
    )
    assert after.status_code == 404


async def test_requires_user_id(api_client: AsyncClient) -> None:
    # Missing the tenant query param -> validation error.
    resp = await api_client.get("/api/v1/memories")
    assert resp.status_code == 422
