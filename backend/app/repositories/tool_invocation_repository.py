"""Data-access layer for tool_invocations (append-only audit; no commit)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PermissionTier, ToolDecision, ToolRunStatus
from app.models.tool_invocation import ToolInvocation


async def record_invocation(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    run_id: uuid.UUID,
    agent_key: str,
    tool_key: str,
    args: dict | None,
    tier: PermissionTier,
    decision: ToolDecision,
    status: ToolRunStatus,
    decision_reason: str | None = None,
    output_ref: dict | None = None,
    error: str | None = None,
    cost_tokens: int = 0,
    cost_usd: Decimal | float = 0,
) -> ToolInvocation:
    """Insert one audit row (flush-only)."""
    invocation = ToolInvocation(
        user_id=user_id,
        run_id=run_id,
        agent_key=agent_key,
        tool_key=tool_key,
        args=args,
        tier=tier,
        decision=decision,
        status=status,
        decision_reason=decision_reason,
        output_ref=output_ref,
        error=error,
        cost_tokens=cost_tokens,
        cost_usd=Decimal(str(cost_usd)),
        finished_at=datetime.now(UTC),
    )
    session.add(invocation)
    await session.flush()
    return invocation


async def list_for_run(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[ToolInvocation]:
    """Return a run's tool-call audit rows in creation order (tenant-scoped)."""
    stmt = (
        select(ToolInvocation)
        .where(
            ToolInvocation.run_id == run_id,
            ToolInvocation.user_id == user_id,
        )
        .order_by(ToolInvocation.created_at.asc())
    )
    return list((await session.execute(stmt)).scalars().all())
