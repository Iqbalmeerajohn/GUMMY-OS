"""Data-access layer for memory embeddings (persistence only, no commit)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_embedding import MemoryEmbedding


async def get_embedding(
    session: AsyncSession,
    *,
    memory_id: uuid.UUID,
    embedding_model: str,
) -> MemoryEmbedding | None:
    """Fetch a memory's embedding for a given model, if it exists."""
    stmt = select(MemoryEmbedding).where(
        MemoryEmbedding.memory_id == memory_id,
        MemoryEmbedding.embedding_model == embedding_model,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_embedding(
    session: AsyncSession,
    *,
    memory_id: uuid.UUID,
    embedding_model: str,
    embedding_dimension: int,
    content_hash: str,
    embedding_vector: list[float],
) -> MemoryEmbedding:
    """Insert a new embedding row and flush."""
    embedding = MemoryEmbedding(
        memory_id=memory_id,
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
    embedding: MemoryEmbedding,
    *,
    embedding_vector: list[float],
    content_hash: str,
    embedding_dimension: int,
) -> MemoryEmbedding:
    """Overwrite an embedding in place (memory content changed) and flush."""
    embedding.embedding_vector = embedding_vector
    embedding.content_hash = content_hash
    embedding.embedding_dimension = embedding_dimension
    await session.flush()
    return embedding


async def list_embeddings(
    session: AsyncSession, *, memory_id: uuid.UUID
) -> list[MemoryEmbedding]:
    """Return all embeddings for a memory (across models)."""
    stmt = select(MemoryEmbedding).where(MemoryEmbedding.memory_id == memory_id)
    return list((await session.execute(stmt)).scalars().all())
