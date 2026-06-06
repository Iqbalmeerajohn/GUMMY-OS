"""Schemas for semantic search and embedding endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import DEFAULT_SEARCH_LIMIT, MAX_SEARCH_LIMIT
from app.models.enums import MemoryCategory, MemoryStatus


class MemorySearchRequest(BaseModel):
    """A semantic search query."""

    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=DEFAULT_SEARCH_LIMIT, ge=1, le=MAX_SEARCH_LIMIT)
    category: MemoryCategory | None = None
    include_archived: bool = False

    @field_validator("query")
    @classmethod
    def _strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be empty or whitespace")
        return stripped


class MemorySearchResult(BaseModel):
    """A single ranked memory with its similarity score."""

    id: uuid.UUID
    user_id: uuid.UUID
    category: MemoryCategory
    content: str
    importance_score: float
    confidence_score: float
    status: MemoryStatus
    similarity_score: float
    created_at: datetime
    updated_at: datetime


class MemorySearchResponse(BaseModel):
    """Ranked results for a search query."""

    query: str
    count: int
    results: list[MemorySearchResult]


class MemoryEmbeddingResponse(BaseModel):
    """Embedding metadata (the raw vector is intentionally not returned)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    memory_id: uuid.UUID
    embedding_model: str
    embedding_dimension: int
    content_hash: str
    created_at: datetime
