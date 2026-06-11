"""Pydantic schemas for tasks (the M8 wire contract)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import TaskStatus

TASK_TITLE_MAX_LENGTH = 200


class TaskCreate(BaseModel):
    """Payload to create a task."""

    title: str = Field(min_length=1, max_length=TASK_TITLE_MAX_LENGTH)
    goal_id: uuid.UUID | None = None
    agent_key: str | None = Field(default=None, max_length=64)
    seq: int = Field(default=0, ge=0)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("title must not be empty or whitespace")
        return stripped


class TaskUpdate(BaseModel):
    """Partial update; at least one field must be provided (service-checked)."""

    title: str | None = Field(
        default=None, min_length=1, max_length=TASK_TITLE_MAX_LENGTH
    )
    status: TaskStatus | None = None
    goal_id: uuid.UUID | None = None
    agent_key: str | None = Field(default=None, max_length=64)
    seq: int | None = Field(default=None, ge=0)
    result_ref: dict | None = None


class TaskResponse(BaseModel):
    """A task as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    goal_id: uuid.UUID | None
    agent_key: str | None
    agent_run_id: uuid.UUID | None
    title: str
    status: TaskStatus
    seq: int
    result_ref: dict | None
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    """A paginated list of tasks."""

    items: list[TaskResponse]
    total: int
    limit: int
    offset: int
