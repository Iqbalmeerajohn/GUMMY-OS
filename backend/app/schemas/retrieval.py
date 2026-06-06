"""Schemas for the hybrid retrieval endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.constants import DEFAULT_RETRIEVAL_LIMIT, MAX_RETRIEVAL_LIMIT
from app.models.enums import MemoryCategory, MemoryStatus


class MemoryRetrievalRequest(BaseModel):
    """A hybrid retrieval query."""

    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=DEFAULT_RETRIEVAL_LIMIT, ge=1, le=MAX_RETRIEVAL_LIMIT)
    category: MemoryCategory | None = None
    include_archived: bool = False
    reinforce: bool = True

    @field_validator("query")
    @classmethod
    def _strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be empty or whitespace")
        return stripped


class RetrievedMemory(BaseModel):
    """A ranked memory with its full score breakdown."""

    id: uuid.UUID
    user_id: uuid.UUID
    category: MemoryCategory
    content: str
    importance_score: float
    confidence_score: float
    status: MemoryStatus
    recall_count: int
    semantic_similarity: float
    recency_score: float
    final_score: float
    created_at: datetime
    updated_at: datetime


class MemoryRetrievalResponse(BaseModel):
    """Top-ranked memories for a query."""

    query: str
    count: int
    results: list[RetrievedMemory]
