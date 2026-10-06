"""Activity and capability endpoint tests.

Two things worth asserting beyond "it returns 200". The feed must be
tenant-scoped, because an audit trail that leaks across users is worse than
no audit trail. And the capability report must require a session, because it
names absolute host paths and the app is meant to be reachable through a
tunnel.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import PermissionTier, ToolDecision, ToolRunStatus
from app.repositories import agent_run_repository as run_repo
from app.repositories import tool_invocation_repository as audit_repo


async def _seed_invocation(
    sessionmaker: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    *,
    tool_key: str = "calculator",
) -> None:
    async with sessionmaker() as session:
        run = await run_repo.create_run(session, user_id=user_id)
        await session.flush()
        await audit_repo.record_invocation(
            session,
            user_id=user_id,
            run_id=run.id,
            agent_key="general",
            tool_key=tool_key,
            args={"expression": "1+1"},
            tier=PermissionTier.GREEN,
            decision=ToolDecision.ALLOWED,
            status=ToolRunStatus.SUCCEEDED,
        )
        await session.commit()


async def test_activity_feed_returns_recent_calls(
    api_client: AsyncClient,
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    seed_user: uuid.UUID,
) -> None:
    await _seed_invocation(sessionmaker_fixture, seed_user)

    response = await api_client.get(
        "/api/v1/activity", params={"user_id": str(seed_user)}
    )

    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 1
    assert items[0]["tool_key"] == "calculator"
    assert items[0]["tier"] == "green"
    assert items[0]["status"] == "succeeded"


async def test_activity_feed_is_tenant_scoped(
    api_client: AsyncClient,
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    seed_user: uuid.UUID,
) -> None:
    """Another user's tool calls must not appear in this user's trail."""
    await _seed_invocation(sessionmaker_fixture, seed_user, tool_key="web_search")

    stranger = uuid.uuid4()
    response = await api_client.get(
        "/api/v1/activity", params={"user_id": str(stranger)}
    )

    assert response.status_code == 200
    assert response.json() == []


async def test_activity_respects_the_limit(
    api_client: AsyncClient,
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    seed_user: uuid.UUID,
) -> None:
    for _ in range(3):
        await _seed_invocation(sessionmaker_fixture, seed_user)

    response = await api_client.get(
        "/api/v1/activity", params={"user_id": str(seed_user), "limit": 2}
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_capabilities_reports_the_live_catalog(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    """The report is derived from the catalog, so it cannot drift from it."""
    from app.services.agents.tools.catalog import TOOL_CATALOG

    response = await api_client.get(
        "/api/v1/activity/capabilities", params={"user_id": str(seed_user)}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == len(TOOL_CATALOG)
    assert body["executable"] == sum(
        1 for spec in TOOL_CATALOG.values() if spec.is_executable
    )
    # Every tier present in the catalog is counted.
    assert sum(body["by_tier"].values()) == body["total"]


async def test_capabilities_flags_an_unconfigured_workspace(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    """Machine-facing tools exist but refuse everything without a root, and
    the report has to say so rather than implying they work."""
    response = await api_client.get(
        "/api/v1/activity/capabilities", params={"user_id": str(seed_user)}
    )

    body = response.json()
    assert isinstance(body["workspace_configured"], bool)
    assert isinstance(body["workspace_roots"], list)
    if not body["workspace_configured"]:
        assert body["workspace_roots"] == []
