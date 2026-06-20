"""Schemas for the memory-confidence diagnostics endpoint.

Answers, for a given query, the four lifecycle questions that matter when a fact
isn't recalled: is it stored, is it retrievable, with what score, and would it be
injected into the prompt.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.models.enums import MemoryCategory


class DiagnosticMemory(BaseModel):
    """One retrieved memory with its scores and prompt-inclusion verdict."""

    id: uuid.UUID
    category: MemoryCategory
    content: str
    importance_score: float
    confidence_score: float
    semantic_similarity: float
    recency_score: float
    final_score: float
    # Whether this memory survived token-budget/limit selection and would
    # actually be placed in the prompt's <memory> block.
    included_in_prompt: bool


class MemoryDiagnosticsResponse(BaseModel):
    """A full memory-confidence trace for one query."""

    query: str
    # Whether automatic extraction is even on — the #1 cause of "I don't know".
    consent_mode: str
    extraction_enabled: bool
    total_memories: int
    retrieved_count: int
    included_count: int
    results: list[DiagnosticMemory]
    # The exact <memory> block text that would be injected for this query.
    prompt_memory_block: str


class MemoryDiagnosticsRequest(BaseModel):
    """A diagnostics query."""

    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=50)
