"""Post-commit enrichment dispatcher seam (Phase 2, M4).

A single shared trigger fired *after* a turn commits — one watermark/delta window
drives every enrichment, instead of three independent cadences (PHASE2_PLAN.md
§21.1). This module is the **seam only**: the consumers below are intentional
NO-OP STUBS, wired in later milestones:

  * title backfill            → M5
  * rolling summary (+ embed) → M5
  * memory extraction         → M6 (consent-gated, via the existing Memory Engine)

For M4 the dispatcher runs the stubs (which do nothing) so the call site, ordering,
and tests are in place. A later milestone moves dispatch off the request path onto
a background worker (mirroring ``embedding_worker``); the turn service already calls
it only after the unit of work has committed.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class EnrichmentJob:
    """The unit of work handed to each enrichment consumer."""

    conversation_id: uuid.UUID
    user_id: uuid.UUID


async def _backfill_title(job: EnrichmentJob) -> None:
    """NO-OP stub — title generation lands in M5."""
    return None


async def _refresh_rolling_summary(job: EnrichmentJob) -> None:
    """NO-OP stub — rolling/closing summaries land in M5."""
    return None


async def _extract_memories(job: EnrichmentJob) -> None:
    """NO-OP stub — conversation→memory extraction lands in M6."""
    return None


# The ordered enrichment consumers. M5/M6 replace the stub bodies above; this
# tuple is the registry the dispatcher iterates.
ENRICHMENT_CONSUMERS: tuple[Callable[[EnrichmentJob], Awaitable[None]], ...] = (
    _backfill_title,
    _refresh_rolling_summary,
    _extract_memories,
)


async def dispatch(*, conversation_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Run the enrichment consumers for a committed turn (no-ops in M4)."""
    job = EnrichmentJob(conversation_id=conversation_id, user_id=user_id)
    for consumer in ENRICHMENT_CONSUMERS:
        await consumer(job)
