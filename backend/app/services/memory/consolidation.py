"""Memory consolidation — keep one true fact per thing Gummy knows.

Without this, every mention of the same fact appends another row. That is not
merely untidy; it actively degrades the product in two measurable ways:

* **Recall gets slower.** Instant recall refuses to answer when two stored
  memories score equally well, because choosing between them would be guessing.
  Duplicates manufacture exactly that tie, pushing questions that should be
  answered in well under a second onto the ~3 s model path.
* **Recall gets wrong.** When a fact changes ("I moved to Bangalore"), an
  append-only store holds both the old and new answer with nothing to separate
  them, so retrieval can confidently surface the stale one.

Similarity is measured with PostgreSQL trigram matching rather than embeddings,
deliberately. Consolidation runs on the *write* path, and an embedding call
there would add a network round-trip to every fact saved. Trigrams are computed
in the database, cost roughly a millisecond, and are strong at precisely the
near-duplicate shapes that occur here ("Lives in Vizag" vs "Tester lives in
Vizag"). Embedding-based merging of semantically-equal-but-lexically-different
facts ("Works at Acme" / "Employed by Acme Corp") is a separate, slower pass
that belongs in the background worker, not here.

On SQLite (the fast test suite) the trigram step is skipped and only exact
normalized matching applies, so behaviour degrades safely rather than erroring.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory, MemoryStatus
from app.models.memory import Memory

logger = logging.getLogger(__name__)

# Above this trigram similarity, two memories are treated as the same fact.
# Chosen to catch restatements ("Name is Iqbal" / "The user's name is Iqbal")
# while leaving genuinely different facts in the same category alone. Set too
# low, distinct facts get merged and information is lost — the worse failure,
# which is why this sits well above the 0.3 default pg_trgm threshold.
_NEAR_DUPLICATE_THRESHOLD = 0.72

# How much a repeated mention strengthens a memory. Small on purpose: repetition
# is weak evidence of importance, and a large step would let chatter outrank
# facts the user stated once and deliberately.
_REINFORCEMENT_STEP = 0.05
_MAX_SCORE = 1.0

_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s]")


class Resolution(StrEnum):
    """What consolidation decided to do with an incoming fact."""

    NEW = "new"  # nothing similar; store it
    DUPLICATE = "duplicate"  # already known; reinforce, store nothing
    SUPERSEDES = "supersedes"  # a better version of a known fact


@dataclass(frozen=True)
class ConsolidationDecision:
    """The outcome of checking an incoming fact against what is already stored."""

    resolution: Resolution
    existing: Memory | None = None
    similarity: float = 0.0


def normalize(content: str) -> str:
    """Canonical form for equality checks: lowercase, unpunctuated, single-spaced."""
    lowered = _PUNCTUATION.sub(" ", content.lower())
    return _WHITESPACE.sub(" ", lowered).strip()


def _is_more_specific(incoming: str, existing: str) -> bool:
    """True when the incoming fact carries strictly more information.

    Used to decide direction when two statements describe the same thing: the
    longer one is kept only if it *contains* the shorter, which distinguishes an
    elaboration ("Lives in Vizag" → "Lives in Vizag, India") from a genuine
    change of fact ("Lives in Vizag" → "Lives in Bangalore"). A changed fact is
    also a supersede, but on recency rather than on length.
    """
    return normalize(existing) in normalize(incoming) and len(incoming) > len(existing)


async def _candidates(
    session: AsyncSession, *, user_id: uuid.UUID, category: MemoryCategory
) -> list[Memory]:
    """Active memories in the same category — the only plausible duplicates."""
    result = await session.scalars(
        select(Memory).where(
            Memory.user_id == user_id,
            Memory.category == category,
            Memory.status == MemoryStatus.ACTIVE,
            Memory.deleted_at.is_(None),
        )
    )
    return list(result)


async def _trigram_similarity(session: AsyncSession, left: str, right: str) -> float:
    """pg_trgm similarity in [0, 1]; 0.0 when unavailable (e.g. SQLite)."""
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return 0.0
    try:
        value = await session.scalar(
            text("SELECT similarity(:a, :b)"), {"a": left, "b": right}
        )
    except Exception:
        logger.debug("trigram similarity unavailable; exact matching only")
        return 0.0
    return float(value or 0.0)


async def resolve(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    category: MemoryCategory,
    content: str,
) -> ConsolidationDecision:
    """Decide whether an incoming fact is new, already known, or an update."""
    candidates = await _candidates(session, user_id=user_id, category=category)
    if not candidates:
        return ConsolidationDecision(Resolution.NEW)

    incoming_norm = normalize(content)

    # Exact match first: free, and the most common duplicate by far (the same
    # fact re-extracted from a later turn of the same conversation).
    for memory in candidates:
        if normalize(memory.content) == incoming_norm:
            return ConsolidationDecision(Resolution.DUPLICATE, memory, 1.0)

    best: Memory | None = None
    best_similarity = 0.0
    for memory in candidates:
        similarity = await _trigram_similarity(
            session, incoming_norm, normalize(memory.content)
        )
        if similarity > best_similarity:
            best, best_similarity = memory, similarity

    if best is None or best_similarity < _NEAR_DUPLICATE_THRESHOLD:
        return ConsolidationDecision(Resolution.NEW, similarity=best_similarity)

    if _is_more_specific(content, best.content):
        return ConsolidationDecision(Resolution.SUPERSEDES, best, best_similarity)
    return ConsolidationDecision(Resolution.DUPLICATE, best, best_similarity)


def reinforce(memory: Memory) -> Memory:
    """Strengthen a memory the user has just restated.

    Repetition is evidence, so confidence rises; importance rises more slowly
    because how often something is mentioned is not the same as how much it
    matters. Both are clamped so a chatty topic cannot saturate the ranking.
    """
    memory.confidence_score = min(
        _MAX_SCORE, (memory.confidence_score or 0.0) + _REINFORCEMENT_STEP
    )
    memory.importance_score = min(
        _MAX_SCORE, (memory.importance_score or 0.0) + _REINFORCEMENT_STEP / 2
    )
    return memory


def supersede(memory: Memory) -> Memory:
    """Retire a memory that a newer statement replaces.

    Marked SUPERSEDED rather than deleted: the old value stays auditable in the
    user's memory timeline, and retrieval already filters to ACTIVE, so a
    superseded fact stops influencing answers immediately.
    """
    memory.status = MemoryStatus.SUPERSEDED
    return memory
