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

import asyncio
import hashlib
from collections import OrderedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.models.memory_embedding import MemoryEmbedding
from app.repositories import memory_embedding_repository as embed_repo
from app.services.embeddings.base import EmbeddingProvider, SupportsAsyncEmbedding

# Query-embedding cache. Every chat turn embeds the user's message before it can
# retrieve, so this sits directly on the critical path. Users repeat and rephrase
# themselves constantly ("what do you know about me", "hi", follow-ups in a
# thread), and an exact repeat is the single cheapest latency win available:
# a cache hit turns a network round-trip into a dict lookup.
#
# Bounded because it is per-process and unbounded growth would be a slow leak.
# Keyed by (model, normalized text) so switching models can never serve a vector
# of the wrong width from the previous model.
_QUERY_CACHE_MAX_ENTRIES = 512


class EmbeddingService:
    """Owns the lifecycle of a memory's vector embedding."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider
        self._query_cache: OrderedDict[tuple[str, str], list[float]] = OrderedDict()

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
            user_id=memory.user_id,
            memory_id=memory.id,
            embedding_model=self._provider.model_name,
            embedding_dimension=self._provider.dimension,
            content_hash=content_hash,
            embedding_vector=vector,
        )

    async def embed_query(self, text: str) -> list[float]:
        """Embed a free-text search query, without blocking the event loop.

        Three tiers, cheapest first:
          1. an in-process cache hit (a repeated or rephrased-identical query);
          2. the provider's native async path, when it has one;
          3. the synchronous provider offloaded to a worker thread.

        Tier 3 matters as much as tier 1: calling a blocking HTTP provider
        directly from async code stalls the event loop for every concurrent
        request, not just this one.
        """
        key = (self._provider.model_name, text.strip())
        cached = self._query_cache.get(key)
        if cached is not None:
            self._query_cache.move_to_end(key)  # LRU: mark as recently used
            return cached

        if isinstance(self._provider, SupportsAsyncEmbedding):
            vector = await self._provider.aembed_text(text)
        else:
            vector = await asyncio.to_thread(self._provider.embed_text, text)

        self._query_cache[key] = vector
        if len(self._query_cache) > _QUERY_CACHE_MAX_ENTRIES:
            self._query_cache.popitem(last=False)  # evict least-recently-used
        return vector
