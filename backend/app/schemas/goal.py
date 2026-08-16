"""Pydantic schemas for goals + milestones (the M5 wire contract)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import AgentContext, GoalPriority, GoalStatus

GOAL_TITLE_MAX_LENGTH = 200
GOAL_CATEGORY_MAX_LENGTH = 64
MILESTONE_TITLE_MAX_LENGTH = 200


def _require_non_blank(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be empty or whitespace")
    return stripped


# ── Milestones ────────────────────────────────────────────────────────────────


class MilestoneCreate(BaseModel):
    """Payload to add a milestone to a goal."""

    title: str = Field(min_length=1, max_length=MILESTONE_TITLE_MAX_LENGTH)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        return _require_non_blank(value)


class MilestoneUpdate(BaseModel):
    """Partial milestone update (service rejects an empty payload)."""

    title: str | None = Field(
        default=None, min_length=1, max_length=MILESTONE_TITLE_MAX_LENGTH
    )
    completed: bool | None = None
    order_index: int | None = Field(default=None, ge=0)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        return _require_non_blank(value) if value is not None else None


class MilestoneResponse(BaseModel):
    """A milestone as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    goal_id: uuid.UUID
    title: str
    completed: bool
    completed_at: datetime | None
    order_index: int
    created_at: datetime
    updated_at: datetime


# ── Goals ─────────────────────────────────────────────────────────────────────


class GoalCreate(BaseModel):
    """Payload to create a goal."""

    title: str = Field(min_length=1, max_length=GOAL_TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=GOAL_CATEGORY_MAX_LENGTH)
    agent_context: AgentContext = AgentContext.GENERAL
    priority: GoalPriority = GoalPriority.MEDIUM
    progress_percentage: int = Field(default=0, ge=0, le=100)
    target_date: datetime | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        return _require_non_blank(value)

    @field_validator("category")
    @classmethod
    def _strip_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class GoalUpdate(BaseModel):
    """Partial update; at least one field must be provided (service-checked)."""

    title: str | None = Field(
        default=None, min_length=1, max_length=GOAL_TITLE_MAX_LENGTH
    )
    description: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=GOAL_CATEGORY_MAX_LENGTH)
    status: GoalStatus | None = None
    agent_context: AgentContext | None = None
    priority: GoalPriority | None = None
    progress_percentage: int | None = Field(default=None, ge=0, le=100)
    target_date: datetime | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        return _require_non_blank(value) if value is not None else None


class GoalResponse(BaseModel):
    """A goal as returned by the API, with its milestones."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: str | None
    category: str | None
    status: GoalStatus
    priority: GoalPriority
    agent_context: AgentContext
    progress_percentage: int
    target_date: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    milestones: list[MilestoneResponse] = Field(default_factory=list)


class GoalListResponse(BaseModel):
    """A paginated list of goals."""

    items: list[GoalResponse]
    total: int
    limit: int
    offset: int


# ── Goal Intelligence (M5.5): conversation-detected candidates ────────────────


class GoalCandidate(BaseModel):
    """A goal-like statement detected in a user message (M5.5).

    Produced by the deterministic :mod:`app.services.goals.goal_extraction_service`
    and surfaced to the client for **explicit confirmation** — it is never
    auto-created, mirroring the memory-consent philosophy (consent before
    persistence). The client renders it as a "Goal Detected" prompt.
    """

    title: str
    description: str | None = None
    priority: GoalPriority = GoalPriority.MEDIUM
    target_date: datetime | None = None


class GoalFromConversationCreate(GoalCreate):
    """Accept payload: a confirmed candidate the user chose to turn into a goal.

    Extends :class:`GoalCreate` with the originating conversation so the
    creation can be traced back to where the goal was detected (``goal_source =
    conversation``).
    """

    conversation_id: uuid.UUID | None = None


class GoalCandidateDismiss(BaseModel):
    """Reject payload: the user dismissed a detected candidate.

    Carries just enough to record the rejection on the ``goal.confirm`` trace
    (no goal is created).
    """

    title: str = Field(min_length=1, max_length=GOAL_TITLE_MAX_LENGTH)
    priority: GoalPriority = GoalPriority.MEDIUM
    target_date: datetime | None = None
    conversation_id: uuid.UUID | None = None


class GoalStatsResponse(BaseModel):
    """Aggregate goal counts for the dashboard."""

    active: int
    completed: int
    archived: int
    total: int
    completion_rate: float
