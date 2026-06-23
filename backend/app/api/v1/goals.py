"""Goal endpoints (``/api/v1/goals``) — thin HTTP over the goals services (M5).

Covers goal CRUD, the status actions (complete / archive), dashboard stats,
and milestone creation under a goal. Milestone-scoped mutations
(``/api/v1/milestones/{id}``) live in :mod:`app.api.v1.milestones`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserId, DbSession
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.models.enums import GoalStatus
from app.repositories import goal_repository
from app.schemas.goal import (
    GoalCandidateDismiss,
    GoalCreate,
    GoalFromConversationCreate,
    GoalListResponse,
    GoalResponse,
    GoalStatsResponse,
    GoalUpdate,
    MilestoneCreate,
    MilestoneResponse,
)
from app.services.goals import goal_service, milestone_service

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post(
    "",
    response_model=GoalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a goal",
)
async def create_goal(
    payload: GoalCreate,
    user_id: CurrentUserId,
    db: DbSession,
) -> GoalResponse:
    goal = await goal_service.create_goal(db, user_id=user_id, payload=payload)
    return GoalResponse.model_validate(goal)


@router.post(
    "/from-conversation",
    response_model=GoalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a goal from a confirmed conversation candidate",
)
async def create_goal_from_conversation(
    payload: GoalFromConversationCreate,
    user_id: CurrentUserId,
    db: DbSession,
) -> GoalResponse:
    """Accept path: the user clicked *Create Goal* on a detected candidate.

    Creates the goal (traced as ``goal.confirm`` → ``goal.create_from_
    conversation``). Goals are never created without this explicit action.
    """
    goal = await goal_service.accept_goal_candidate(
        db,
        user_id=user_id,
        payload=payload,
        conversation_id=payload.conversation_id,
    )
    return GoalResponse.model_validate(goal)


@router.post(
    "/from-conversation/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dismiss a detected goal candidate (records the rejection)",
)
async def dismiss_goal_candidate(
    payload: GoalCandidateDismiss,
    user_id: CurrentUserId,
) -> None:
    """Reject path: the user clicked *Dismiss*. Records ``goal.confirm``
    (``accepted=false``) for observability; creates nothing."""
    goal_service.reject_goal_candidate(
        title=payload.title,
        priority=payload.priority,
        target_date=payload.target_date,
    )


@router.get("", response_model=GoalListResponse, summary="List goals")
async def list_goals(
    user_id: CurrentUserId,
    db: DbSession,
    status: GoalStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GoalListResponse:
    items, total = await goal_service.list_goals(
        db, user_id=user_id, status=status, limit=limit, offset=offset
    )
    return GoalListResponse(
        items=[GoalResponse.model_validate(g) for g in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/stats",
    response_model=GoalStatsResponse,
    summary="Aggregate goal counts for the dashboard",
)
async def goal_stats(
    user_id: CurrentUserId,
    db: DbSession,
) -> GoalStatsResponse:
    counts = await goal_repository.count_by_status(db, user_id=user_id)
    active = counts.get(GoalStatus.ACTIVE, 0)
    completed = counts.get(GoalStatus.COMPLETED, 0)
    archived = counts.get(GoalStatus.ARCHIVED, 0)
    total = active + completed + archived
    # Completion rate over the goals being worked on or finished (archived,
    # i.e. set-aside, goals are excluded so abandoning work doesn't skew it).
    denominator = active + completed
    completion_rate = (completed / denominator) if denominator else 0.0
    return GoalStatsResponse(
        active=active,
        completed=completed,
        archived=archived,
        total=total,
        completion_rate=round(completion_rate, 4),
    )


@router.get(
    "/{goal_id}", response_model=GoalResponse, summary="Get a goal by id"
)
async def get_goal(
    goal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> GoalResponse:
    goal = await goal_service.get_goal(db, user_id=user_id, goal_id=goal_id)
    return GoalResponse.model_validate(goal)


@router.patch(
    "/{goal_id}",
    response_model=GoalResponse,
    summary="Update a goal (title / category / status / priority / progress)",
)
async def update_goal(
    goal_id: uuid.UUID,
    payload: GoalUpdate,
    user_id: CurrentUserId,
    db: DbSession,
) -> GoalResponse:
    goal = await goal_service.update_goal(
        db, user_id=user_id, goal_id=goal_id, payload=payload
    )
    return GoalResponse.model_validate(goal)


@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a goal and its milestones",
)
async def delete_goal(
    goal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> None:
    await goal_service.delete_goal(db, user_id=user_id, goal_id=goal_id)


@router.post(
    "/{goal_id}/complete",
    response_model=GoalResponse,
    summary="Mark a goal completed",
)
async def complete_goal(
    goal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> GoalResponse:
    goal = await goal_service.complete_goal(
        db, user_id=user_id, goal_id=goal_id
    )
    return GoalResponse.model_validate(goal)


@router.post(
    "/{goal_id}/archive",
    response_model=GoalResponse,
    summary="Archive a goal",
)
async def archive_goal(
    goal_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> GoalResponse:
    goal = await goal_service.archive_goal(
        db, user_id=user_id, goal_id=goal_id
    )
    return GoalResponse.model_validate(goal)


@router.post(
    "/{goal_id}/milestones",
    response_model=MilestoneResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a milestone to a goal",
)
async def add_milestone(
    goal_id: uuid.UUID,
    payload: MilestoneCreate,
    user_id: CurrentUserId,
    db: DbSession,
) -> MilestoneResponse:
    milestone = await milestone_service.add_milestone(
        db, user_id=user_id, goal_id=goal_id, payload=payload
    )
    return MilestoneResponse.model_validate(milestone)
