"""Action-approval API tests (Phase 3, M10)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import PermissionTier
from app.models.user import User
from app.repositories import action_approval_repository as approval_repo

_TENANT = uuid.uuid4()
_OTHER = uuid.uuid4()


def _q(user: uuid.UUID = _TENANT) -> dict[str, str]:
    return {"user_id": str(user)}


async def _seed_pending(
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    user: uuid.UUID = _TENANT,
) -> uuid.UUID:
    """Seed a user + one pending approval directly (the gate is unit-tested
    in test_approval_service; the API tests exercise the endpoints)."""
    async with sessionmaker_fixture() as session:
        if await session.get(User, user) is None:
            session.add(User(id=user, email=f"{user}@api.test"))
            await session.flush()
        approval = await approval_repo.create_pending(
            session,
            user_id=user,
            agent_key="powerful",
            action_kind="email_send",
            tier=PermissionTier.YELLOW,
            preview={"tool_key": "email_send", "args": {"to": "x@y.z"}},
        )
        await session.commit()
        return approval.id


async def test_list_and_get_actions(
    api_client: AsyncClient,
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
) -> None:
    approval_id = await _seed_pending(sessionmaker_fixture)
    listed = await api_client.get(
        "/api/v1/actions", params={**_q(), "status": "pending"}
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(approval_id)
    assert body["items"][0]["preview"]["tool_key"] == "email_send"

    fetched = await api_client.get(f"/api/v1/actions/{approval_id}", params=_q())
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "pending"


async def test_approve_then_conflict(
    api_client: AsyncClient,
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
) -> None:
    approval_id = await _seed_pending(sessionmaker_fixture)
    approved = await api_client.post(
        f"/api/v1/actions/{approval_id}/approve", params=_q()
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["decided_at"] is not None

    again = await api_client.post(f"/api/v1/actions/{approval_id}/reject", params=_q())
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "approval_already_decided"


async def test_reject(
    api_client: AsyncClient,
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
) -> None:
    approval_id = await _seed_pending(sessionmaker_fixture)
    rejected = await api_client.post(
        f"/api/v1/actions/{approval_id}/reject", params=_q()
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


async def test_foreign_tenant_404(
    api_client: AsyncClient,
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
) -> None:
    approval_id = await _seed_pending(sessionmaker_fixture)
    fetched = await api_client.get(f"/api/v1/actions/{approval_id}", params=_q(_OTHER))
    assert fetched.status_code == 404
    assert fetched.json()["error"]["code"] == "approval_not_found"
    decided = await api_client.post(
        f"/api/v1/actions/{approval_id}/approve", params=_q(_OTHER)
    )
    assert decided.status_code == 404
    listed = await api_client.get("/api/v1/actions", params=_q(_OTHER))
    assert listed.json()["total"] == 0


@pytest.mark.parametrize("verb", ["approve", "reject"])
async def test_unknown_approval_404(api_client: AsyncClient, verb: str) -> None:
    response = await api_client.post(
        f"/api/v1/actions/{uuid.uuid4()}/{verb}", params=_q()
    )
    assert response.status_code == 404
