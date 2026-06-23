"""Goal service — lifecycle of durable, user-facing goals (M5 Goals System).

Owns validation and the unit of work (commit); the repository flushes.
Progress is derived from milestones when a goal has any (kept in sync by
:mod:`app.services.goals.milestone_service` via :func:`recompute_progress`);
otherwise ``progress_percentage`` is whatever the user last set.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.enums import GoalStatus
from app.models.goal import Goal
from app.observability import langfuse as langfuse_obs
from app.repositories import goal_repository as repo
from app.repositories import milestone_repository as milestone_repo
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


def _now() -> datetime:
    return datetime.now(UTC)


async def create_goal(
    session: AsyncSession, *, user_id: uuid.UUID, payload: GoalCreate
) -> Goal:
    """Create an active goal. Commits."""
    goal = await repo.create_goal(
        session,
        user_id=user_id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        agent_context=payload.agent_context,
        priority=payload.priority,
        progress_percentage=payload.progress_percentage,
        target_date=payload.target_date,
    )
    await session.commit()
    await session.refresh(goal)
    return goal


async def get_goal(
    session: AsyncSession, *, user_id: uuid.UUID, goal_id: uuid.UUID
) -> Goal:
    """Fetch one goal or raise 404 (foreign tenants see 404, never 403)."""
    with langfuse_obs.observe_operation(
        "goal.get", metadata={"goal_id": str(goal_id)}
    ):
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
    with langfuse_obs.observe_operation(
        "goal.list",
        metadata={
            "status": status.value if status else None,
            "limit": limit,
            "offset": offset,
        },
    ) as span:
        items, total = await repo.list_goals(
            session,
            user_id=user_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        span.update(metadata={"returned": len(items), "total": total})
    return items, total


def _apply_status_side_effects(goal: Goal, new_status: GoalStatus) -> None:
    """Keep ``completed_at`` consistent with a status transition."""
    if new_status == GoalStatus.COMPLETED:
        if goal.completed_at is None:
            goal.completed_at = _now()
    else:
        goal.completed_at = None


async def update_goal(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    payload: GoalUpdate,
) -> Goal:
    """Apply a partial update. Empty payload → 400. Commits.

    A manual ``progress_percentage`` is honored only for goals without
    milestones; otherwise milestone-derived progress is authoritative and the
    manual value is ignored.
    """
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise EmptyUpdateError()
    goal = await get_goal(session, user_id=user_id, goal_id=goal_id)

    if "status" in changes:
        _apply_status_side_effects(goal, changes["status"])
    if "progress_percentage" in changes:
        _, total = await milestone_repo.completion_counts(
            session, goal_id=goal.id, user_id=user_id
        )
        if total > 0:
            # Milestone-derived progress wins; drop the manual override.
            changes.pop("progress_percentage")

    for field, value in changes.items():
        setattr(goal, field, value)
    await session.commit()
    await session.refresh(goal)
    return goal


async def complete_goal(
    session: AsyncSession, *, user_id: uuid.UUID, goal_id: uuid.UUID
) -> Goal:
    """Mark a goal completed (records ``completed_at``). Commits."""
    with langfuse_obs.observe_operation(
        "goal.complete", metadata={"goal_id": str(goal_id)}
    ):
        goal = await get_goal(session, user_id=user_id, goal_id=goal_id)
        goal.status = GoalStatus.COMPLETED
        _apply_status_side_effects(goal, GoalStatus.COMPLETED)
        await session.commit()
        await session.refresh(goal)
    return goal


async def archive_goal(
    session: AsyncSession, *, user_id: uuid.UUID, goal_id: uuid.UUID
) -> Goal:
    """Archive a goal (hidden from agents). Commits."""
    goal = await get_goal(session, user_id=user_id, goal_id=goal_id)
    goal.status = GoalStatus.ARCHIVED
    _apply_status_side_effects(goal, GoalStatus.ARCHIVED)
    await session.commit()
    await session.refresh(goal)
    return goal


async def delete_goal(
    session: AsyncSession, *, user_id: uuid.UUID, goal_id: uuid.UUID
) -> None:
    """Delete a goal and its milestones (cascade). Commits."""
    goal = await get_goal(session, user_id=user_id, goal_id=goal_id)
    await session.delete(goal)
    await session.commit()


async def recompute_progress(
    session: AsyncSession, *, user_id: uuid.UUID, goal: Goal
) -> None:
    """Recompute a goal's progress from its milestones (no commit).

    ``progress = round(completed / total * 100)`` when milestones exist; left
    untouched (manual) when the goal has none. Caller owns the commit.
    """
    completed, total = await milestone_repo.completion_counts(
        session, goal_id=goal.id, user_id=user_id
    )
    if total > 0:
        goal.progress_percentage = round(completed / total * 100)
