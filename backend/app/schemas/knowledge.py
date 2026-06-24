"""Schemas for the Unified Knowledge & Retrieval Engine (M7).

The engine fuses memories, goals, and files into a single ranked context layer.
These schemas are the **API surface** of that engine: the diagnostics endpoint
(`GET /knowledge/diagnostics`) returns a full trace of what was retrieved from
each source, how it was ranked across sources, and what would actually be packed
into the prompt's ``<knowledge>`` block.

The internal domain types (``KnowledgeItem`` / ``UnifiedKnowledgeContext``) live
in :mod:`app.services.knowledge.knowledge_retrieval_service` as pure dataclasses;
these Pydantic models only shape the HTTP response.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class KnowledgeDiagnosticItem(BaseModel):
    """One ranked knowledge item with its provenance and scores."""

    # Provenance — every item keeps its origin ("memory" | "goal" | "file").
    source: str
    # A display label for the item: memory category, goal title, or filename.
    label: str
    # The renderable content (truncated for the diagnostics payload).
    content: str
    # The item's native score from its own source (memory hybrid score, goal
    # score, or file retrieval score) before cross-source normalization.
    source_score: float
    # The cross-source comparable score the ranker assigned (what ordered it
    # against items from the other sources).
    rank_score: float
    # Whether this item survived dedupe + token-budget selection and would be
    # placed into the prompt's ``<knowledge>`` block.
    included_in_prompt: bool


class KnowledgeDiagnosticsResponse(BaseModel):
    """A full trace of one query through the unified knowledge pipeline."""

    query: str
    # Per-source counts of what was retrieved (before ranking/compression).
    memories_used: int
    goals_used: int
    files_used: int
    # Which sources actually contributed candidates (provenance for the turn).
    sources_used: list[str]
    # The fused, cross-source ranking (highest first), each tagged with origin.
    ranked_items: list[KnowledgeDiagnosticItem]
    # Token estimate of the compiled ``<knowledge>`` block that would be injected.
    token_estimate: int
    # The exact ``<knowledge>`` block text that would be injected for this query.
    knowledge_block: str


class KnowledgeDiagnosticsRequest(BaseModel):
    """A diagnostics query (the GET endpoint uses query params, not this body)."""

    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=20, ge=1, le=50)
