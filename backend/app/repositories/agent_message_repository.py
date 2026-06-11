"""Data-access layer for agent_messages (append-only; persistence only).

The inter-agent audit trail: one row per orchestrator-mediated hop. Rows are
immutable; ``seq`` is the monotonic per-run ordinal (the ``messages.seq``
pattern, enforced by ``UNIQUE(run_id, seq)``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_message import AgentMessage
from app.models.enums import AgentMessageRole


async def next_seq(session: AsyncSession, run_id: uuid.UUID) -> int:
    """Return the next monotonic hop ordinal for a run (1-based)."""
    current = await session.scalar(
        select(func.max(AgentMessage.seq)).where(
            AgentMessage.run_id == run_id
        )
    )
    return int(current or 0) + 1


async def append_message(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    from_agent: str,
    to_agent: str | None,
    role: AgentMessageRole,
    payload: dict,
) -> AgentMessage:
    """Insert one audited hop (next seq assigned) and flush."""
    message = AgentMessage(
        run_id=run_id,
        user_id=user_id,
        from_agent=from_agent,
        to_agent=to_agent,
        role=role,
        payload=payload,
        seq=await next_seq(session, run_id),
    )
    session.add(message)
    await session.flush()
    return message


async def list_for_run(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[AgentMessage]:
    """Return a run's inter-agent hops in order (tenant-scoped)."""
    stmt = (
        select(AgentMessage)
        .where(
            AgentMessage.run_id == run_id,
            AgentMessage.user_id == user_id,
        )
        .order_by(AgentMessage.seq.asc())
    )
    return list((await session.execute(stmt)).scalars().all())
