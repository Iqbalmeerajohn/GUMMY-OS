"""Pydantic schemas for goals (the M8 wire contract)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import AgentContext, GoalStatus

GOAL_TITLE_MAX_LENGTH = 200


class GoalCreate(BaseModel):
    """Payload to create a goal."""

    title: str = Field(min_length=1, max_length=GOAL_TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=4000)
    agent_context: AgentContext = AgentContext.GENERAL
    priority: int = Field(default=0, ge=0, le=100)
    target_date: datetime | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("title must not be empty or whitespace")
        return stripped


class GoalUpdate(BaseModel):
    """Partial update; at least one field must be provided (service-checked)."""

    title: str | None = Field(
        default=None, min_length=1, max_length=GOAL_TITLE_MAX_LENGTH
    )
    description: str | None = Field(default=None, max_length=4000)
    status: GoalStatus | None = None
    agent_context: AgentContext | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    target_date: datetime | None = None


class GoalResponse(BaseModel):
    """A goal as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: str | None
    status: GoalStatus
    agent_context: AgentContext
    priority: int
    target_date: datetime | None
    created_at: datetime
    updated_at: datetime


class GoalListResponse(BaseModel):
    """A paginated list of goals."""

    items: list[GoalResponse]
    total: int
    limit: int
    offset: int
