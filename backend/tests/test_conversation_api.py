"""API-layer tests for the Conversation endpoints (M3)."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MessageRole
from app.repositories import message_repository as msg_repo


def _params(user_id: uuid.UUID, **extra: str | int) -> dict[str, str | int]:
    return {"user_id": str(user_id), **extra}


async def test_create_conversation_returns_201(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.post(
        "/api/v1/conversations",
        params=_params(seed_user),
        json={"title": "Planning", "agent_context": "career"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Planning"
    assert body["agent_context"] == "career"
    assert body["status"] == "active"
    assert body["pinned"] is False
    assert body["message_count"] == 0
    assert uuid.UUID(body["id"])


async def test_create_blank_title_is_422(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    resp = await api_client.post(
        "/api/v1/conversations",
        params=_params(seed_user),
        json={"title": "   "},
    )
    assert resp.status_code == 422


async def test_list_conversations(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    for _ in range(2):
        await api_client.post(
            "/api/v1/conversations", params=_params(seed_user), json={}
        )
    resp = await api_client.get(
        "/api/v1/conversations", params=_params(seed_user, limit=10)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["limit"] == 10


async def test_get_conversation_and_404(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    created = (
        await api_client.post(
            "/api/v1/conversations", params=_params(seed_user), json={}
        )
    ).json()
    ok = await api_client.get(
        f"/api/v1/conversations/{created['id']}", params=_params(seed_user)
    )
    assert ok.status_code == 200

    missing = await api_client.get(
        f"/api/v1/conversations/{uuid.uuid4()}", params=_params(seed_user)
    )
    assert missing.status_code == 404


async def test_patch_rename_pin_archive(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    created = (
        await api_client.post(
            "/api/v1/conversations", params=_params(seed_user), json={}
        )
    ).json()
    resp = await api_client.patch(
        f"/api/v1/conversations/{created['id']}",
        params=_params(seed_user),
        json={"title": "Renamed", "pinned": True, "status": "archived"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Renamed"
    assert body["pinned"] is True
    assert body["status"] == "archived"


async def test_patch_empty_is_400(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    created = (
        await api_client.post(
            "/api/v1/conversations", params=_params(seed_user), json={}
        )
    ).json()
    resp = await api_client.patch(
        f"/api/v1/conversations/{created['id']}",
        params=_params(seed_user),
        json={},
    )
    assert resp.status_code == 400


async def test_delete_then_404(api_client: AsyncClient, seed_user: uuid.UUID) -> None:
    created = (
        await api_client.post(
            "/api/v1/conversations", params=_params(seed_user), json={}
        )
    ).json()
    deleted = await api_client.delete(
        f"/api/v1/conversations/{created['id']}", params=_params(seed_user)
    )
    assert deleted.status_code == 204
    after = await api_client.get(
        f"/api/v1/conversations/{created['id']}", params=_params(seed_user)
    )
    assert after.status_code == 404


async def test_conversation_is_tenant_isolated(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    created = (
        await api_client.post(
            "/api/v1/conversations", params=_params(seed_user), json={}
        )
    ).json()
    other_user = uuid.uuid4()
    # A different tenant cannot see it (list empty, get 404).
    listing = await api_client.get("/api/v1/conversations", params=_params(other_user))
    assert listing.json()["total"] == 0
    get_resp = await api_client.get(
        f"/api/v1/conversations/{created['id']}", params=_params(other_user)
    )
    assert get_resp.status_code == 404


async def test_message_history_empty_and_404(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    created = (
        await api_client.post(
            "/api/v1/conversations", params=_params(seed_user), json={}
        )
    ).json()
    empty = await api_client.get(
        f"/api/v1/conversations/{created['id']}/messages",
        params=_params(seed_user),
    )
    assert empty.status_code == 200
    assert empty.json()["total"] == 0

    missing = await api_client.get(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        params=_params(seed_user),
    )
    assert missing.status_code == 404


async def test_message_history_serializes_metadata(
    api_client: AsyncClient, db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    # api_client and db_session share the same in-memory engine (one fixture).
    created = (
        await api_client.post(
            "/api/v1/conversations", params=_params(seed_user), json={}
        )
    ).json()
    await msg_repo.append_message(
        db_session,
        conversation_id=uuid.UUID(created["id"]),
        user_id=seed_user,
        role=MessageRole.ASSISTANT,
        content="hi",
        model="claude-x",
        extra_metadata={"citations": [1]},
    )
    await db_session.commit()

    resp = await api_client.get(
        f"/api/v1/conversations/{created['id']}/messages",
        params=_params(seed_user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["role"] == "assistant"
    assert item["model"] == "claude-x"
    assert item["metadata"] == {"citations": [1]}
    assert item["seq"] == 1
