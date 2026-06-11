"""Goal service — lifecycle of durable goals (Phase 3, M8).

Owns validation and the unit of work (commit); the repository flushes.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.enums import GoalStatus
from app.models.goal import Goal
from app.repositories import goal_repository as repo
from app.schemas.goal import GoalCreate, GoalUpdate


class GoalNotFoundError(AppError):
    """Raised when a goal does not exist for this tenant."""

    def __init__(self, goal_id: uuid.UUID) -> None:
        super().__init__(
            f"Goal {goal_id} not found.",
            code="goal_not_found",
            status_code=404,
        )


class EmptyUpdateError(AppError):
    """Raised when an update request carries no changeable fields."""

    def __init__(self) -> None:
        super().__init__(
            "No fields provided to update.",
            code="empty_update",
            status_code=400,
        )


async def create_goal(
    session: AsyncSession, *, user_id: uuid.UUID, payload: GoalCreate
) -> Goal:
    """Create an active goal. Commits."""
    goal = await repo.create_goal(
        session,
        user_id=user_id,
        title=payload.title,
        description=payload.description,
        agent_context=payload.agent_context,
        priority=payload.priority,
        target_date=payload.target_date,
    )
    await session.commit()
    await session.refresh(goal)
    return goal


async def get_goal(
    session: AsyncSession, *, user_id: uuid.UUID, goal_id: uuid.UUID
) -> Goal:
    """Fetch one goal or raise 404 (foreign tenants see 404, never 403)."""
    goal = await repo.get_goal(session, goal_id=goal_id, user_id=user_id)
    if goal is None:
        raise GoalNotFoundError(goal_id)
    return goal


async def list_goals(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    status: GoalStatus | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Goal], int]:
    """List goals (priority desc, newest first)."""
    return await repo.list_goals(
        session, user_id=user_id, status=status, limit=limit, offset=offset
    )


async def update_goal(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    payload: GoalUpdate,
) -> Goal:
    """Apply a partial update. Empty payload → 400. Commits."""
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise EmptyUpdateError()
    goal = await get_goal(session, user_id=user_id, goal_id=goal_id)
    for field, value in changes.items():
        setattr(goal, field, value)
    await session.commit()
    await session.refresh(goal)
    return goal


async def complete_goal(
    session: AsyncSession, *, user_id: uuid.UUID, goal_id: uuid.UUID
) -> Goal:
    """Mark a goal done. Commits."""
    goal = await get_goal(session, user_id=user_id, goal_id=goal_id)
    goal.status = GoalStatus.DONE
    await session.commit()
    await session.refresh(goal)
    return goal
