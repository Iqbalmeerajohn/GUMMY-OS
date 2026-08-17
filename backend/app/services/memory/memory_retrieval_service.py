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
    RETRIEVAL_MIN_SEMANTIC_SIMILARITY,
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
from app.services.memory import consolidation


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


def recency_reference(memory: Memory) -> datetime:
    """The moment a memory's recency should be measured from.

    ``occurred_at`` when the memory records something that *happened* (a calendar
    event, "shipped M8 last Tuesday"), else ``created_at`` — when the fact was
    learned. A note taken today about last month should decay as last month.

    Deliberately NOT ``last_recalled_at``. Retrieval sets ``last_recalled_at``
    on everything it surfaces, so scoring recency from it forms a feedback loop:
    a retrieved memory resets to maximum recency, which raises its next score,
    which makes it more likely to be retrieved again. Once a memory entered the
    top N it was structurally advantaged in staying there, regardless of whether
    it was ever relevant again. Recency should describe the fact, not its own
    retrieval history.
    """
    return memory.occurred_at or memory.created_at


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


def _dedupe(ranked: list[RankedMemory]) -> list[RankedMemory]:
    """Drop memories whose content repeats one already selected (highest first).

    Consolidation prevents duplicates being *written*, but it only runs on the
    write path and only from M9 onward, so stores predating it still hold exact
    repeats — the live database has "Building GUMMY, a personal AI operating
    system" stored twice, both active. Injecting the same fact twice wastes the
    token budget and, worse, manufactures the score tie that makes instant recall
    decline a question it could have answered.

    Normalization is ``consolidation.normalize`` rather than a second
    implementation, so "already known" means the same thing on both paths.
    """
    seen: set[str] = set()
    out: list[RankedMemory] = []
    for item in ranked:
        key = consolidation.normalize(item.memory.content)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


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
    min_semantic: float | None = None,
) -> list[RankedMemory]:
    """Embed the query, rank candidates by the hybrid score, and reinforce.

    Candidates must clear a **semantic** relevance floor before they are ranked,
    so a memory with no topical relationship to the query cannot be carried into
    the prompt by its importance or recency alone. Returning fewer than ``limit``
    results — or none at all — is the normal, intended outcome for a question the
    user's memories have nothing to say about.

    ``min_semantic`` overrides that floor: pass ``0.0`` for a diagnostic view that
    must show rejected candidates too. ``None`` uses the configured default.

    ``query_vector`` may be supplied by a caller that already embedded the query
    (e.g. to time embedding separately); when ``None`` the query is embedded here.
    """
    now = now or datetime.now(UTC)
    floor = RETRIEVAL_MIN_SEMANTIC_SIMILARITY if min_semantic is None else min_semantic

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
        below_floor = 0
        for memory, distance in candidates:
            similarity = _clamp01(1.0 - distance)
            # The relevance gate, before any blending. A memory that is not about
            # the query is not made relevant by being important or recent.
            if similarity < floor:
                below_floor += 1
                continue
            recency = compute_recency_score(recency_reference(memory), now=now)
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
        deduped = _dedupe(ranked)
        top = deduped[:limit]

        span.update(
            output={
                "candidates": len(candidates),
                "below_floor": below_floor,
                "duplicates_dropped": len(ranked) - len(deduped),
                "returned": len(top),
                "floor": floor,
                "top_score": round(top[0].final_score, 4) if top else None,
                "embedding_model": embedding_service.model_name,
            }
        )

        if reinforce and top:
            await reinforce_memories(session, [item.memory for item in top], now=now)
            await session.commit()
            # `updated_at` is expired by the server-side onupdate; reload eagerly
            # so callers never trigger a lazy load outside the async session.
            for item in top:
                await session.refresh(item.memory)

        return top
