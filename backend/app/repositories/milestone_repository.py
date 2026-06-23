"""Data-access layer for goal milestones (persistence only, no commit)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goal_milestone import GoalMilestone


async def create_milestone(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    title: str,
    order_index: int,
) -> GoalMilestone:
    """Insert a milestone (incomplete) and flush to populate id."""
    milestone = GoalMilestone(
        user_id=user_id,
        goal_id=goal_id,
        title=title,
        order_index=order_index,
    )
    session.add(milestone)
    await session.flush()
    return milestone


async def get_milestone(
    session: AsyncSession,
    *,
    milestone_id: uuid.UUID,
    user_id: uuid.UUID,
) -> GoalMilestone | None:
    """Fetch a single tenant-scoped milestone by id, if it exists."""
    stmt = select(GoalMilestone).where(
        GoalMilestone.id == milestone_id,
        GoalMilestone.user_id == user_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_for_goal(
    session: AsyncSession,
    *,
    goal_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[GoalMilestone]:
    """All milestones for a goal, in user-defined order."""
    stmt = (
        select(GoalMilestone)
        .where(
            GoalMilestone.goal_id == goal_id,
            GoalMilestone.user_id == user_id,
        )
        .order_by(GoalMilestone.order_index, GoalMilestone.created_at)
    )
    return list((await session.execute(stmt)).scalars().all())


async def completion_counts(
    session: AsyncSession,
    *,
    goal_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[int, int]:
    """Return ``(completed, total)`` milestone counts for a goal."""
    total = await session.scalar(
        select(func.count())
        .select_from(GoalMilestone)
        .where(
            GoalMilestone.goal_id == goal_id,
            GoalMilestone.user_id == user_id,
        )
    )
    completed = await session.scalar(
        select(func.count())
        .select_from(GoalMilestone)
        .where(
            GoalMilestone.goal_id == goal_id,
            GoalMilestone.user_id == user_id,
            GoalMilestone.completed.is_(True),
        )
    )
    return int(completed or 0), int(total or 0)


async def max_order_index(
    session: AsyncSession,
    *,
    goal_id: uuid.UUID,
    user_id: uuid.UUID,
) -> int | None:
    """Highest ``order_index`` among a goal's milestones, or ``None`` if empty."""
    return await session.scalar(
        select(func.max(GoalMilestone.order_index)).where(
            GoalMilestone.goal_id == goal_id,
            GoalMilestone.user_id == user_id,
        )
    )


async def delete_milestone(
    session: AsyncSession, *, milestone: GoalMilestone
) -> None:
    """Delete a milestone (caller owns the commit)."""
    await session.delete(milestone)
    await session.flush()
