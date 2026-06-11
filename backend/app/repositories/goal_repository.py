"""Data-access layer for goals (persistence only, no commit)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AgentContext, GoalStatus
from app.models.goal import Goal


async def create_goal(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    title: str,
    description: str | None = None,
    agent_context: AgentContext = AgentContext.GENERAL,
    priority: int = 0,
    target_date: datetime | None = None,
) -> Goal:
    """Insert a new active goal and flush to populate id."""
    goal = Goal(
        user_id=user_id,
        title=title,
        description=description,
        agent_context=agent_context,
        priority=priority,
        target_date=target_date,
    )
    session.add(goal)
    await session.flush()
    return goal


async def get_goal(
    session: AsyncSession,
    *,
    goal_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Goal | None:
    """Fetch a single tenant-scoped goal by id, if it exists."""
    stmt = select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_goals(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    status: GoalStatus | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Goal], int]:
    """Return a page of goals (priority desc, newest first) and the total."""
    filters = [Goal.user_id == user_id]
    if status is not None:
        filters.append(Goal.status == status)
    total = await session.scalar(
        select(func.count()).select_from(Goal).where(*filters)
    )
    stmt = (
        select(Goal)
        .where(*filters)
        .order_by(Goal.priority.desc(), Goal.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), int(total or 0)


async def list_active(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
) -> list[Goal]:
    """Active goals for context packing (priority desc)."""
    stmt = (
        select(Goal)
        .where(Goal.user_id == user_id, Goal.status == GoalStatus.ACTIVE)
        .order_by(Goal.priority.desc(), Goal.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
