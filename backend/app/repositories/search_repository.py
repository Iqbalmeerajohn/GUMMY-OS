"""Semantic search over memories using pgvector cosine similarity.

The ranking runs entirely in PostgreSQL: a join from ``memories`` to
``memory_embeddings`` ordered by cosine distance (``<=>``), tenant-scoped and
filtered to live (non-deleted) memories. This requires the pgvector extension and
therefore PostgreSQL (not SQLite).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory, MemoryStatus
from app.models.memory import Memory
from app.models.memory_embedding import MemoryEmbedding


def build_search_statement(
    *,
    user_id: uuid.UUID,
    query_vector: list[float],
    embedding_model: str,
    limit: int,
    include_archived: bool = False,
    category: MemoryCategory | None = None,
) -> Select[Any]:
    """Build the tenant-scoped cosine-similarity ranking statement."""
    # `cosine_distance` is provided by pgvector's comparator; reference the column
    # as Any so the mapping stays mypy-clean without provider-specific stubs.
    embedding_col: Any = MemoryEmbedding.embedding_vector
    distance = embedding_col.cosine_distance(query_vector).label("distance")

    filters = [
        Memory.user_id == user_id,
        Memory.deleted_at.is_(None),
        MemoryEmbedding.embedding_model == embedding_model,
    ]
    if not include_archived:
        filters.append(Memory.status == MemoryStatus.ACTIVE)
    if category is not None:
        filters.append(Memory.category == category)

    return (
        select(Memory, distance)
        .join(MemoryEmbedding, MemoryEmbedding.memory_id == Memory.id)
        .where(*filters)
        .order_by(distance)
        .limit(limit)
    )


async def search_similar_memories(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query_vector: list[float],
    embedding_model: str,
    limit: int,
    include_archived: bool = False,
    category: MemoryCategory | None = None,
) -> list[tuple[Memory, float]]:
    """Return ``(memory, cosine_distance)`` pairs, nearest first."""
    stmt = build_search_statement(
        user_id=user_id,
        query_vector=query_vector,
        embedding_model=embedding_model,
        limit=limit,
        include_archived=include_archived,
        category=category,
    )
    result = await session.execute(stmt)
    return [(row[0], float(row[1])) for row in result.all()]
