"""Activity and capability surfaces (``/api/v1/activity``) — read-only.

Two questions this answers that nothing else did.

**"What has GUMMY been doing?"** Every tool call already lands in
``tool_invocations`` with its tier, decision and outcome, but the only way to
read it was per-run, which means you had to already know which turn you were
interested in. An activity feed is the other direction: newest first, across
everything, so the audit trail is something a person can actually look at
rather than a table only the orchestrator writes to.

**"What can it do?"** The tool catalog is code-defined and fixed at startup,
so the honest answer is knowable exactly rather than described in a README
that drifts. This reports the real catalog, with each tool's tier, whether it
is executable, and where it came from — plus whether the machine-facing tools
have a workspace configured at all, since without one they refuse everything
and the capability is nominal.

Read-only by design: nothing here writes, and the capability report is
derived from code, never from user input.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import CurrentUserId, DbSession
from app.core.config import get_settings
from app.repositories import tool_invocation_repository as tool_repo
from app.services.agents.tools import workspace as workspace_config
from app.services.agents.tools.catalog import list_tools

router = APIRouter(prefix="/activity", tags=["activity"])


class ActivityItem(BaseModel):
    """One tool call, as the audit trail recorded it."""

    id: str
    run_id: str | None = None
    agent_key: str
    tool_key: str
    tier: str
    decision: str
    status: str
    decision_reason: str | None = None
    error: str | None = None
    created_at: str


class CapabilityItem(BaseModel):
    """One tool the running process can offer."""

    key: str
    name: str
    description: str
    category: str
    tier: str
    # False for a modeled tool: declared and gated, but nothing runs.
    executable: bool
    # True for a tool contributed by an external server rather than built in.
    external: bool


class CapabilityReport(BaseModel):
    """What this process can actually do, right now."""

    tools: list[CapabilityItem]
    total: int
    executable: int
    by_tier: dict[str, int]
    # Machine-facing tools refuse every path without a configured workspace,
    # so this is the difference between having them and being able to use them.
    workspace_configured: bool
    workspace_roots: list[str]
    telegram_enabled: bool
    external_tools_enabled: bool
    energy_accounting: bool


@router.get(
    "",
    response_model=list[ActivityItem],
    summary="Recent tool calls across every run, newest first",
)
async def list_activity(
    user_id: CurrentUserId,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ActivityItem]:
    rows = await tool_repo.list_recent(db, user_id=user_id, limit=limit)
    return [
        ActivityItem(
            id=str(row.id),
            run_id=str(row.run_id) if row.run_id else None,
            agent_key=row.agent_key,
            tool_key=row.tool_key,
            tier=row.tier.value,
            decision=row.decision.value,
            status=row.status.value,
            decision_reason=row.decision_reason,
            error=row.error,
            created_at=row.created_at.isoformat(),
        )
        for row in rows
    ]


@router.get(
    "/capabilities",
    response_model=CapabilityReport,
    summary="Every tool this process can offer, and how it is gated",
)
async def capabilities(_user_id: CurrentUserId) -> CapabilityReport:
    """Derived from the live catalog, so it cannot drift from reality.

    Authenticated even though the catalog is the same for every user: the
    report names the configured workspace roots, which are absolute paths on
    the host. Harmless on loopback, a disclosure once the app is reachable
    through a tunnel — and it is reachable through a tunnel by design.

    The user id is unused on purpose: the dependency is here to require a
    valid session, not to scope the result.
    """
    settings = get_settings()
    specs = list_tools()

    by_tier: dict[str, int] = {}
    for spec in specs:
        by_tier[spec.tier.value] = by_tier.get(spec.tier.value, 0) + 1

    space = workspace_config.from_settings()

    return CapabilityReport(
        tools=[
            CapabilityItem(
                key=spec.key,
                name=spec.name,
                description=spec.description,
                category=spec.category,
                tier=spec.tier.value,
                executable=spec.is_executable,
                external=spec.category == "external",
            )
            for spec in specs
        ],
        total=len(specs),
        executable=sum(1 for spec in specs if spec.is_executable),
        by_tier=by_tier,
        workspace_configured=space.configured,
        workspace_roots=space.describe(),
        telegram_enabled=bool(settings.gummy_telegram_bot_token),
        external_tools_enabled=settings.gummy_mcp_enabled,
        energy_accounting=settings.gummy_energy_accounting,
    )
