"""Task endpoints (``/api/v1/tasks``) — thin HTTP over task_service (M8)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserId, DbSession
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.models.enums import TaskStatus
from app.schemas.task import (
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TaskUpdate,
)
from app.services.agents import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
)
async def create_task(
    payload: TaskCreate,
    user_id: CurrentUserId,
    db: DbSession,
) -> TaskResponse:
    task = await task_service.create_task(db, user_id=user_id, payload=payload)
    return TaskResponse.model_validate(task)


@router.get("", response_model=TaskListResponse, summary="List tasks")
async def list_tasks(
    user_id: CurrentUserId,
    db: DbSession,
    status: TaskStatus | None = None,
    goal_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TaskListResponse:
    items, total = await task_service.list_tasks(
        db,
        user_id=user_id,
        status=status,
        goal_id=goal_id,
        limit=limit,
        offset=offset,
    )
    return TaskListResponse(
        items=[TaskResponse.model_validate(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{task_id}", response_model=TaskResponse, summary="Get a task by id")
async def get_task(
    task_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> TaskResponse:
    task = await task_service.get_task(db, user_id=user_id, task_id=task_id)
    return TaskResponse.model_validate(task)


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Update a task (status / retitle / relink / reorder)",
)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    user_id: CurrentUserId,
    db: DbSession,
) -> TaskResponse:
    task = await task_service.update_task(
        db, user_id=user_id, task_id=task_id, payload=payload
    )
    return TaskResponse.model_validate(task)
