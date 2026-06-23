"""Milestone service — manage a goal's checklist steps (M5 Goals System).

Every mutation recomputes the parent goal's derived progress in the same unit
of work, so ``goal.progress_percentage`` is always consistent with milestone
completion. Owns validation and the commit; repositories flush.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.goal_milestone import GoalMilestone
from app.observability import langfuse as langfuse_obs
from app.repositories import milestone_repository as repo
from app.schemas.goal import MilestoneCreate, MilestoneUpdate
from app.services.goals import goal_service


class MilestoneNotFoundError(AppError):
    """Raised when a milestone does not exist for this tenant."""

    def __init__(self, milestone_id: uuid.UUID) -> None:
        super().__init__(
            f"Milestone {milestone_id} not found.",
            code="milestone_not_found",
            status_code=404,
        )


class EmptyMilestoneUpdateError(AppError):
    """Raised when a milestone update carries no changeable fields."""

    def __init__(self) -> None:
        super().__init__(
            "No fields provided to update.",
            code="empty_update",
            status_code=400,
        )


def _now() -> datetime:
    return datetime.now(UTC)


async def get_milestone(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    milestone_id: uuid.UUID,
) -> GoalMilestone:
    """Fetch one milestone or raise 404 (foreign tenants see 404)."""
    milestone = await repo.get_milestone(
        session, milestone_id=milestone_id, user_id=user_id
    )
    if milestone is None:
        raise MilestoneNotFoundError(milestone_id)
    return milestone


async def add_milestone(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    goal_id: uuid.UUID,
    payload: MilestoneCreate,
) -> GoalMilestone:
    """Append a milestone to a goal (ownership-checked) and recompute progress.

    Commits and returns the refreshed parent goal's freshly-created milestone.
    """
    goal = await goal_service.get_goal(
        session, user_id=user_id, goal_id=goal_id
    )
    highest = await repo.max_order_index(
        session, goal_id=goal.id, user_id=user_id
    )
    milestone = await repo.create_milestone(
        session,
        user_id=user_id,
        goal_id=goal.id,
        title=payload.title,
        order_index=(highest + 1) if highest is not None else 0,
    )
    await goal_service.recompute_progress(
        session, user_id=user_id, goal=goal
    )
    await session.commit()
    await session.refresh(milestone)
    return milestone


async def update_milestone(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    milestone_id: uuid.UUID,
    payload: MilestoneUpdate,
) -> GoalMilestone:
    """Apply a partial update; toggling ``completed`` stamps ``completed_at``.

    Recomputes the parent goal's progress in the same transaction. Commits.
    """
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise EmptyMilestoneUpdateError()
    with langfuse_obs.observe_operation(
        "milestone.update",
        metadata={
            "milestone_id": str(milestone_id),
            "fields": sorted(changes.keys()),
        },
    ):
        milestone = await get_milestone(
            session, user_id=user_id, milestone_id=milestone_id
        )

        if "completed" in changes:
            if changes["completed"] and not milestone.completed:
                milestone.completed_at = _now()
            elif not changes["completed"]:
                milestone.completed_at = None
        for field, value in changes.items():
            setattr(milestone, field, value)

        goal = await goal_service.get_goal(
            session, user_id=user_id, goal_id=milestone.goal_id
        )
        await goal_service.recompute_progress(
            session, user_id=user_id, goal=goal
        )
        await session.commit()
        await session.refresh(milestone)
    return milestone


async def delete_milestone(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    milestone_id: uuid.UUID,
) -> None:
    """Delete a milestone and recompute the parent goal's progress. Commits."""
    milestone = await get_milestone(
        session, user_id=user_id, milestone_id=milestone_id
    )
    goal_id = milestone.goal_id
    await repo.delete_milestone(session, milestone=milestone)
    goal = await goal_service.get_goal(
        session, user_id=user_id, goal_id=goal_id
    )
    await goal_service.recompute_progress(
        session, user_id=user_id, goal=goal
    )
    await session.commit()
