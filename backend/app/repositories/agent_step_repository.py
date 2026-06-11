"""Data-access layer for agent_steps (persistence only, no commit).

A step is appended ``running`` when an agent is dispatched and finalized with
its output/status/cost when the handler returns. ``seq`` is the monotonic
per-run ordinal (the ``messages.seq`` pattern): flushed-but-uncommitted rows
are visible within the session, and ``UNIQUE(run_id, seq)`` turns a concurrent
collision into an error rather than silent reordering.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_step import AgentStep
from app.models.enums import StepStatus


async def next_seq(session: AsyncSession, run_id: uuid.UUID) -> int:
    """Return the next monotonic step ordinal for a run (1-based)."""
    current = await session.scalar(
        select(func.max(AgentStep.seq)).where(AgentStep.run_id == run_id)
    )
    return int(current or 0) + 1


async def append_step(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    agent_key: str,
    input: dict | None = None,
) -> AgentStep:
    """Insert a new ``running`` step (next seq assigned) and flush."""
    step = AgentStep(
        run_id=run_id,
        user_id=user_id,
        agent_key=agent_key,
        seq=await next_seq(session, run_id),
        status=StepStatus.RUNNING,
        input=input,
    )
    session.add(step)
    await session.flush()
    return step


async def finish_step(
    session: AsyncSession,
    step: AgentStep,
    *,
    status: StepStatus,
    output: dict | None = None,
    error: str | None = None,
    cost_tokens: int = 0,
    cost_usd: Decimal | float = 0,
) -> AgentStep:
    """Finalize a step: status, output/error, cost, ``finished_at``. Flush-only."""
    step.status = status
    step.output = output
    step.error = error
    step.cost_tokens = cost_tokens
    step.cost_usd = Decimal(str(cost_usd))
    step.finished_at = datetime.now(UTC)
    await session.flush()
    return step


async def list_for_run(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[AgentStep]:
    """Return a run's steps in execution order (tenant-scoped)."""
    stmt = (
        select(AgentStep)
        .where(
            AgentStep.run_id == run_id,
            AgentStep.user_id == user_id,
        )
        .order_by(AgentStep.seq.asc())
    )
    return list((await session.execute(stmt)).scalars().all())
