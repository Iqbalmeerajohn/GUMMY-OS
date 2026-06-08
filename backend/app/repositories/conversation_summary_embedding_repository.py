"""Data-access layer for conversation-summary embeddings (no commit).

A direct mirror of ``memory_embedding_repository`` for the summary vector that
powers semantic conversation search. Persistence only — embedding generation and
sync policy live in the service/worker (see PHASE2_PLAN.md §5/§12).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_summary_embedding import (
    ConversationSummaryEmbedding,
)


async def get_embedding(
    session: AsyncSession,
    *,
    summary_id: uuid.UUID,
    embedding_model: str,
) -> ConversationSummaryEmbedding | None:
    """Fetch a summary's embedding for a given model, if it exists."""
    stmt = select(ConversationSummaryEmbedding).where(
        ConversationSummaryEmbedding.summary_id == summary_id,
        ConversationSummaryEmbedding.embedding_model == embedding_model,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_embedding(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    summary_id: uuid.UUID,
    embedding_model: str,
    embedding_dimension: int,
    content_hash: str,
    embedding_vector: list[float],
) -> ConversationSummaryEmbedding:
    """Insert a new summary embedding row and flush."""
    embedding = ConversationSummaryEmbedding(
        user_id=user_id,
        summary_id=summary_id,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        content_hash=content_hash,
        embedding_vector=embedding_vector,
    )
    session.add(embedding)
    await session.flush()
    return embedding


async def update_embedding(
    session: AsyncSession,
    embedding: ConversationSummaryEmbedding,
    *,
    embedding_vector: list[float],
    content_hash: str,
    embedding_dimension: int,
) -> ConversationSummaryEmbedding:
    """Overwrite a summary embedding in place and flush."""
    embedding.embedding_vector = embedding_vector
    embedding.content_hash = content_hash
    embedding.embedding_dimension = embedding_dimension
    await session.flush()
    return embedding


async def list_embeddings(
    session: AsyncSession, *, summary_id: uuid.UUID
) -> list[ConversationSummaryEmbedding]:
    """Return all embeddings for a summary (across models)."""
    stmt = select(ConversationSummaryEmbedding).where(
        ConversationSummaryEmbedding.summary_id == summary_id
    )
    return list((await session.execute(stmt)).scalars().all())
