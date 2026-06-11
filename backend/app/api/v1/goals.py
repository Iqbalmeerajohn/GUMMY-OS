"""Goal endpoints (``/api/v1/goals``) — thin HTTP over goal_service (M8)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserId, DbSession
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.models.enums import GoalStatus
from app.schemas.goal import (
    GoalCreate,
    GoalListResponse,
    GoalResponse,
    GoalUpdate,
)
from app.services.agents import goal_service

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
    summary="Update a goal (status / priority / retitle / re-tag)",
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
