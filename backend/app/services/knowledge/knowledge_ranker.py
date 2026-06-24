"""KnowledgeRanker — fuse the three sources onto one comparable scale.

Memories, goals, and files each arrive scored on their *own* axis (a memory's
hybrid score, a goal's priority/deadline, a file's retrieval order). The ranker
projects each onto a shared 0–1 "native" score, applies a cross-source weight,
and adds the attachment boost — producing a single ``rank_score`` per item so a
memory, a goal, and a file chunk can be ordered against one another.

Priority order the weights encode (highest first):

    attached files  >  relevant files  >  goals  >  memories

Pure and I/O-free apart from an optional ``now`` for deadline math — fully
unit-testable without a database or model.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

from app.core.constants import (
    KNOWLEDGE_ATTACHMENT_BOOST,
    KNOWLEDGE_FILE_BASE_SCORE,
    KNOWLEDGE_FILE_RANK_DECAY,
    KNOWLEDGE_GOAL_BASE_SCORE,
    KNOWLEDGE_GOAL_DEADLINE_HORIZON_DAYS,
    KNOWLEDGE_SEARCH_BASE_SCORE,
    KNOWLEDGE_SEARCH_RANK_DECAY,
    KNOWLEDGE_WEIGHT_FILE,
    KNOWLEDGE_WEIGHT_GOAL,
    KNOWLEDGE_WEIGHT_GOAL_DEADLINE,
    KNOWLEDGE_WEIGHT_GOAL_PRIORITY,
    KNOWLEDGE_WEIGHT_MEMORY,
    KNOWLEDGE_WEIGHT_SEARCH,
)
from app.models.enums import GOAL_PRIORITY_RANK, GoalPriority
from app.observability import langfuse as langfuse_obs
from app.services.knowledge.knowledge_retrieval_service import (
    SOURCE_FILE,
    SOURCE_GOAL,
    SOURCE_MEMORY,
    SOURCE_SEARCH,
    KnowledgeItem,
    UnifiedKnowledgeContext,
)

# Highest priority rank value (high == 3), used to normalize to [0, 1].
_MAX_PRIORITY_RANK = max(GOAL_PRIORITY_RANK.values())


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _ensure_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def priority_score(priority: str) -> float:
    """Normalize a goal priority to [0, 1] (high → 1.0, low → ~0.33)."""
    try:
        rank = GOAL_PRIORITY_RANK[GoalPriority(priority)]
    except (KeyError, ValueError):
        return 0.0
    return rank / _MAX_PRIORITY_RANK


def deadline_proximity(target: datetime | None, *, now: datetime) -> float:
    """Score deadline urgency in [0, 1].

    A goal due now (or overdue) scores 1.0; one due at the horizon scores 0.0;
    in between it decays linearly. No target date → 0.0 (no urgency signal).
    """
    if target is None:
        return 0.0
    days_left = (_ensure_utc(target) - now).total_seconds() / 86400.0
    if days_left <= 0:
        return 1.0
    if days_left >= KNOWLEDGE_GOAL_DEADLINE_HORIZON_DAYS:
        return 0.0
    return 1.0 - (days_left / KNOWLEDGE_GOAL_DEADLINE_HORIZON_DAYS)


def goal_native_score(item: KnowledgeItem, *, now: datetime) -> float:
    """Blend an active goal's baseline presence, priority, and deadline → [0, 1]."""
    priority = priority_score(str(item.metadata.get("priority", "")))
    deadline = deadline_proximity(item.metadata.get("_target_dt"), now=now)
    return _clamp01(
        KNOWLEDGE_GOAL_BASE_SCORE
        + KNOWLEDGE_WEIGHT_GOAL_PRIORITY * priority
        + KNOWLEDGE_WEIGHT_GOAL_DEADLINE * deadline
    )


def file_native_score(item: KnowledgeItem) -> float:
    """Score a file chunk by its retrieval order (best keyword match leads)."""
    order = int(item.metadata.get("order", 0))
    return KNOWLEDGE_FILE_BASE_SCORE * (KNOWLEDGE_FILE_RANK_DECAY**order)


def search_native_score(item: KnowledgeItem) -> float:
    """Score a web-search hit by its result order (best hit leads, gentle decay)."""
    order = int(item.metadata.get("order", 0))
    return KNOWLEDGE_SEARCH_BASE_SCORE * (KNOWLEDGE_SEARCH_RANK_DECAY**order)


def _score_item(item: KnowledgeItem, *, now: datetime) -> KnowledgeItem:
    """Return a copy of ``item`` with ``source_score`` and ``rank_score`` set."""
    if item.source == SOURCE_MEMORY:
        native = _clamp01(item.source_score)
        rank = KNOWLEDGE_WEIGHT_MEMORY * native
        return dataclasses.replace(item, source_score=native, rank_score=rank)

    if item.source == SOURCE_GOAL:
        native = goal_native_score(item, now=now)
        rank = KNOWLEDGE_WEIGHT_GOAL * native
        return dataclasses.replace(item, source_score=native, rank_score=rank)

    if item.source == SOURCE_FILE:
        native = file_native_score(item)
        rank = KNOWLEDGE_WEIGHT_FILE * native
        if item.metadata.get("attached"):
            rank += KNOWLEDGE_ATTACHMENT_BOOST
        return dataclasses.replace(item, source_score=native, rank_score=rank)

    if item.source == SOURCE_SEARCH:
        # Supplemental: weighted below memory so live results never override the
        # user's own knowledge (priority: attachments > files > goals > memories
        # > search).
        native = search_native_score(item)
        rank = KNOWLEDGE_WEIGHT_SEARCH * native
        return dataclasses.replace(item, source_score=native, rank_score=rank)

    return item


def rank(
    context: UnifiedKnowledgeContext, *, now: datetime | None = None
) -> list[KnowledgeItem]:
    """Score every item across sources and return them sorted (highest first).

    The returned list mixes all three sources on one ``rank_score`` axis. Ties
    are broken stably by source priority (file > goal > memory) then native
    score, so an attached file always leads and goals outrank generic memories
    at equal relevance.
    """
    now = now or datetime.now(UTC)
    with langfuse_obs.observe_operation(
        "knowledge.rank",
        metadata={"items": len(context.all_items)},
    ) as span:
        scored = [_score_item(item, now=now) for item in context.all_items]
        # Source tiebreak: attached/relevant files first, then goals, then
        # memories, then supplemental search — matters when rank_scores are equal.
        tiebreak = {
            SOURCE_FILE: 3,
            SOURCE_GOAL: 2,
            SOURCE_MEMORY: 1,
            SOURCE_SEARCH: 0,
        }
        scored.sort(
            key=lambda i: (i.rank_score, tiebreak.get(i.source, 0), i.source_score),
            reverse=True,
        )
        span.update(
            metadata={
                "ranked": len(scored),
                "top_source": scored[0].source if scored else None,
                "top_score": round(scored[0].rank_score, 4) if scored else None,
            }
        )
        return scored
