"""Data-access layer for agent_runs (persistence only, no commit).

One row per orchestration. The run is created ``running`` inside the turn's
unit of work and finalized (status/cost) before the service commits, so the
trace lands atomically with the conversation messages.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.models.enums import RunStatus, RunTrigger


async def create_run(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    trigger: RunTrigger = RunTrigger.CHAT,
    route_plan: dict | None = None,
) -> AgentRun:
    """Insert a new ``running`` orchestration trace and flush to populate id."""
    run = AgentRun(
        user_id=user_id,
        conversation_id=conversation_id,
        trigger=trigger,
        route_plan=route_plan,
        status=RunStatus.RUNNING,
    )
    session.add(run)
    await session.flush()
    return run


async def get_run(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
) -> AgentRun | None:
    """Fetch a single tenant-scoped run by id, if it exists."""
    stmt = select(AgentRun).where(
        AgentRun.id == run_id,
        AgentRun.user_id == user_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_for_conversation(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    limit: int,
    offset: int = 0,
) -> list[AgentRun]:
    """Return a conversation's runs, newest first (tenant-scoped)."""
    stmt = (
        select(AgentRun)
        .where(
            AgentRun.conversation_id == conversation_id,
            AgentRun.user_id == user_id,
        )
        .order_by(AgentRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).scalars().all())


async def set_status(
    session: AsyncSession,
    run: AgentRun,
    *,
    status: RunStatus,
    error: str | None = None,
) -> AgentRun:
    """Move a run to a terminal/updated status; stamps ``finished_at`` on
    terminal states. Flush-only."""
    run.status = status
    run.error = error
    if status in (RunStatus.SUCCEEDED, RunStatus.FAILED):
        run.finished_at = datetime.now(UTC)
    await session.flush()
    return run


async def add_cost(
    session: AsyncSession,
    run: AgentRun,
    *,
    tokens: int,
    usd: Decimal | float = 0,
) -> AgentRun:
    """Accumulate cost onto a run (called once per completed step)."""
    run.cost_tokens = (run.cost_tokens or 0) + tokens
    run.cost_usd = (run.cost_usd or Decimal("0")) + Decimal(str(usd))
    await session.flush()
    return run
