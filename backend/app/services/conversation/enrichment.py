"""Post-commit enrichment consumers (Phase 2, M5).

A single shared trigger fires after a turn commits; the ``enrichment_worker``
drains the queue and runs these consumers, each in its own session (PHASE2_PLAN.md
§21.1). Every consumer is best-effort and tenant-scoped, flushes through the
services it calls, and lets the worker own the commit.

Status:
  * title backfill   → implemented (M5)
  * rolling summary  → implemented (M5)
  * memory extraction → NO-OP STUB (lands in M6, via the existing Memory Engine)
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.conversation import conversation_service, summary_service
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.llm.base import LLMProvider


@dataclass(frozen=True)
class EnrichmentJob:
    """The unit of work handed to each enrichment consumer."""

    conversation_id: uuid.UUID
    user_id: uuid.UUID


# A consumer: do one enrichment for a job, within the worker-provided session.
Consumer = Callable[
    [AsyncSession, "EnrichmentJob", LLMProvider, EmbeddingService],
    Awaitable[None],
]


async def backfill_title(
    session: AsyncSession,
    job: EnrichmentJob,
    llm: LLMProvider,
    embedding_service: EmbeddingService,
) -> None:
    """Generate a thread title from the first exchange (idempotent, M5)."""
    await conversation_service.backfill_title(
        session,
        user_id=job.user_id,
        conversation_id=job.conversation_id,
        llm=llm,
    )


async def refresh_rolling_summary(
    session: AsyncSession,
    job: EnrichmentJob,
    llm: LLMProvider,
    embedding_service: EmbeddingService,
) -> None:
    """Refresh the rolling summary + its embedding when due (M5)."""
    await summary_service.maybe_refresh_rolling_summary(
        session,
        user_id=job.user_id,
        conversation_id=job.conversation_id,
        llm=llm,
        embedding_service=embedding_service,
    )


async def extract_memories(
    session: AsyncSession,
    job: EnrichmentJob,
    llm: LLMProvider,
    embedding_service: EmbeddingService,
) -> None:
    """NO-OP stub — conversation→memory extraction lands in M6."""
    return None


# Ordered registry the worker iterates (each consumer in its own session).
ENRICHMENT_CONSUMERS: tuple[Consumer, ...] = (
    backfill_title,
    refresh_rolling_summary,
    extract_memories,
)
