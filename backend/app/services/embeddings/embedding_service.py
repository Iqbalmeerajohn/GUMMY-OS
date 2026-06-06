"""Embedding service — generate, dedupe, and maintain memory embeddings.

Responsibilities:
  * generate embeddings via an injected provider
  * detect content changes (via a content hash)
  * avoid duplicate work (skip re-embedding unchanged content)
  * keep embeddings current when a memory is edited (update in place)

The service flushes through the repository but does not commit — the caller owns
the transaction (consistent with the rest of the data layer).
"""

from __future__ import annotations

import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.models.memory_embedding import MemoryEmbedding
from app.repositories import memory_embedding_repository as embed_repo
from app.services.embeddings.base import EmbeddingProvider


class EmbeddingService:
    """Owns the lifecycle of a memory's vector embedding."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider

    @property
    def model_name(self) -> str:
        return self._provider.model_name

    @property
    def dimension(self) -> int:
        return self._provider.dimension

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Stable hash of the embeddable text (whitespace-normalized)."""
        normalized = content.strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    async def sync_memory_embedding(
        self,
        session: AsyncSession,
        *,
        memory: Memory,
    ) -> MemoryEmbedding:
        """Create or update this memory's embedding for the active model.

        No-op (returns the existing row) when the content hash is unchanged —
        this is the dedupe path that avoids recomputing embeddings.
        """
        content_hash = self.compute_content_hash(memory.content)
        existing = await embed_repo.get_embedding(
            session,
            memory_id=memory.id,
            embedding_model=self._provider.model_name,
        )
        if existing is not None and existing.content_hash == content_hash:
            return existing

        vector = self._provider.embed_text(memory.content)

        if existing is not None:
            return await embed_repo.update_embedding(
                session,
                existing,
                embedding_vector=vector,
                content_hash=content_hash,
                embedding_dimension=self._provider.dimension,
            )
        return await embed_repo.create_embedding(
            session,
            memory_id=memory.id,
            embedding_model=self._provider.model_name,
            embedding_dimension=self._provider.dimension,
            content_hash=content_hash,
            embedding_vector=vector,
        )

    async def embed_query(self, text: str) -> list[float]:
        """Embed a free-text search query."""
        return self._provider.embed_text(text)
