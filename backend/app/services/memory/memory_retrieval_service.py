"""Hybrid retrieval engine.

Blends semantic similarity with importance, confidence, and recency to rank a
user's memories for a query, then reinforces the ones actually surfaced.

The ranking math is pure (and unit-tested without a database); candidate fetching
delegates to the pgvector semantic search (PostgreSQL-only).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    CONFIDENCE_REINFORCEMENT_STEP,
    DEFAULT_RETRIEVAL_LIMIT,
    IMPORTANCE_REINFORCEMENT_STEP,
    RECENCY_HALF_LIFE_DAYS,
    REINFORCEMENT_COOLDOWN_SECONDS,
    RETRIEVAL_CANDIDATE_MULTIPLIER,
    RETRIEVAL_WEIGHT_CONFIDENCE,
    RETRIEVAL_WEIGHT_IMPORTANCE,
    RETRIEVAL_WEIGHT_RECENCY,
    RETRIEVAL_WEIGHT_SEMANTIC,
)
from app.models.enums import MemoryCategory
from app.models.memory import Memory
from app.observability import langfuse as langfuse_obs
from app.repositories import memory_repository as repo
from app.repositories import search_repository as search_repo
from app.services.embeddings.embedding_service import EmbeddingService


@dataclass(frozen=True)
class RankedMemory:
    """A memory with its computed ranking signals."""

    memory: Memory
    semantic_similarity: float
    recency_score: float
    final_score: float


# ── Pure ranking helpers (no I/O) ─────────────────────────────────────────────


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _ensure_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def compute_recency_score(reference: datetime, *, now: datetime) -> float:
    """Exponential decay: halves every ``RECENCY_HALF_LIFE_DAYS`` days."""
    age_days = max((now - _ensure_utc(reference)).total_seconds() / 86400.0, 0.0)
    return 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)


def compute_hybrid_score(
    *,
    semantic_similarity: float,
    importance_score: float,
    confidence_score: float,
    recency_score: float,
) -> float:
    """Weighted blend of the four ranking signals (result in [0, 1])."""
    return (
        RETRIEVAL_WEIGHT_SEMANTIC * _clamp01(semantic_similarity)
        + RETRIEVAL_WEIGHT_IMPORTANCE * _clamp01(importance_score)
        + RETRIEVAL_WEIGHT_CONFIDENCE * _clamp01(confidence_score)
        + RETRIEVAL_WEIGHT_RECENCY * _clamp01(recency_score)
    )


def reinforced_scores(
    importance_score: float, confidence_score: float
) -> tuple[float, float]:
    """Diminishing-returns bump toward 1.0 (hard-capped)."""
    new_importance = min(
        1.0,
        importance_score + IMPORTANCE_REINFORCEMENT_STEP * (1.0 - importance_score),
    )
    new_confidence = min(
        1.0,
        confidence_score + CONFIDENCE_REINFORCEMENT_STEP * (1.0 - confidence_score),
    )
    return new_importance, new_confidence


# ── Reinforcement & retrieval (I/O) ───────────────────────────────────────────


async def reinforce_memories(
    session: AsyncSession,
    memories: list[Memory],
    *,
    now: datetime,
) -> None:
    """Reinforce retrieved memories.

    Always counts the recall; bumps importance/confidence at most once per
    cooldown window (so a burst of retrievals cannot inflate scores).
    """
    cooldown = timedelta(seconds=REINFORCEMENT_COOLDOWN_SECONDS)
    for memory in memories:
        last = memory.last_recalled_at
        should_bump = last is None or (now - _ensure_utc(last)) >= cooldown

        importance = memory.importance_score
        confidence = memory.confidence_score
        if should_bump:
            importance, confidence = reinforced_scores(importance, confidence)

        await repo.apply_recall(
            session,
            memory,
            recall_count=memory.recall_count + 1,
            importance_score=importance,
            confidence_score=confidence,
            last_recalled_at=now,
        )


async def retrieve_memories(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    embedding_service: EmbeddingService,
    limit: int = DEFAULT_RETRIEVAL_LIMIT,
    category: MemoryCategory | None = None,
    include_archived: bool = False,
    reinforce: bool = True,
    now: datetime | None = None,
    query_vector: list[float] | None = None,
) -> list[RankedMemory]:
    """Embed the query, rank candidates by the hybrid score, and reinforce.

    ``query_vector`` may be supplied by a caller that already embedded the query
    (e.g. to time embedding separately); when ``None`` the query is embedded here.
    """
    now = now or datetime.now(UTC)

    with langfuse_obs.observe_retrieval(
        input=query,
        metadata={
            "limit": limit,
            "category": category.value if category else None,
            "include_archived": include_archived,
            "reinforce": reinforce,
        },
    ) as span:
        if query_vector is None:
            query_vector = await embedding_service.embed_query(query)
        candidates = await search_repo.search_similar_memories(
            session,
            user_id=user_id,
            query_vector=query_vector,
            embedding_model=embedding_service.model_name,
            limit=limit * RETRIEVAL_CANDIDATE_MULTIPLIER,
            include_archived=include_archived,
            category=category,
        )

        ranked: list[RankedMemory] = []
        for memory, distance in candidates:
            similarity = _clamp01(1.0 - distance)
            recency = compute_recency_score(
                memory.last_recalled_at or memory.created_at, now=now
            )
            score = compute_hybrid_score(
                semantic_similarity=similarity,
                importance_score=memory.importance_score,
                confidence_score=memory.confidence_score,
                recency_score=recency,
            )
            ranked.append(
                RankedMemory(
                    memory=memory,
                    semantic_similarity=similarity,
                    recency_score=recency,
                    final_score=score,
                )
            )

        ranked.sort(key=lambda item: item.final_score, reverse=True)
        top = ranked[:limit]

        span.update(
            output={
                "candidates": len(candidates),
                "returned": len(top),
                "top_score": round(top[0].final_score, 4) if top else None,
                "embedding_model": embedding_service.model_name,
            }
        )

        if reinforce and top:
            await reinforce_memories(
                session, [item.memory for item in top], now=now
            )
            await session.commit()
            # `updated_at` is expired by the server-side onupdate; reload eagerly
            # so callers never trigger a lazy load outside the async session.
            for item in top:
                await session.refresh(item.memory)

        return top
