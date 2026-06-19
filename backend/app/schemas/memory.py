"""Pydantic schemas for the Memory CRUD API (the wire contract)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import (
    MAX_CONTENT_LENGTH,
    MAX_SCORE,
    MIN_CONTENT_LENGTH,
    MIN_SCORE,
)
from app.models.enums import MemoryCategory, MemoryStatus


def _validate_content(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        raise ValueError("content must not be empty or whitespace")
    return stripped


class MemoryCreate(BaseModel):
    """Payload to create a memory."""

    category: MemoryCategory
    content: str = Field(min_length=MIN_CONTENT_LENGTH, max_length=MAX_CONTENT_LENGTH)
    importance_score: float | None = Field(default=None, ge=MIN_SCORE, le=MAX_SCORE)
    confidence_score: float | None = Field(default=None, ge=MIN_SCORE, le=MAX_SCORE)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str) -> str:
        validated = _validate_content(value)
        assert validated is not None  # min_length guarantees non-None
        return validated


class MemoryUpdate(BaseModel):
    """Partial update payload. Only provided fields are changed."""

    content: str | None = Field(
        default=None, min_length=MIN_CONTENT_LENGTH, max_length=MAX_CONTENT_LENGTH
    )
    category: MemoryCategory | None = None
    importance_score: float | None = Field(default=None, ge=MIN_SCORE, le=MAX_SCORE)
    confidence_score: float | None = Field(default=None, ge=MIN_SCORE, le=MAX_SCORE)

    @field_validator("content")
    @classmethod
    def _strip_content(cls, value: str | None) -> str | None:
        return _validate_content(value)


class MemoryResponse(BaseModel):
    """A memory as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    category: MemoryCategory
    content: str
    importance_score: float
    confidence_score: float
    status: MemoryStatus
    created_at: datetime
    updated_at: datetime


class MemoryListResponse(BaseModel):
    """A paginated list of memories."""

    items: list[MemoryResponse]
    total: int
    limit: int
    offset: int
