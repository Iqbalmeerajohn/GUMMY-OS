"""Background enrichment worker (Phase 2, M5).

Mirrors ``embedding_worker``: a single asyncio task drains a queue of enrichment
jobs (one per committed turn). Each consumer (title backfill, rolling summary, and
the M6 extraction stub) runs in its **own** DB session so a failure in one is
isolated and never blocks the others or crashes the worker. Keeping enrichment off
the request path is the whole point — the turn enqueues and returns immediately.

A module-level ``enrichment_worker`` singleton is enqueued to by the turn service
and started/stopped by the app lifespan.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.observability import capture_exception
from app.core.tenant_context import set_current_user_id
from app.services.conversation.enrichment import (
    ENRICHMENT_CONSUMERS,
    EnrichmentJob,
)
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class EnrichmentWorker:
    """Consumes enrichment jobs from an in-memory queue (best-effort)."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[EnrichmentJob] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None
        self._llm: LLMProvider | None = None
        self._embedding_service: EmbeddingService | None = None
        self.is_running = False

    def configure(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        llm: LLMProvider,
        embedding_service: EmbeddingService,
    ) -> None:
        """Inject runtime dependencies (called from the app lifespan/tests)."""
        self._sessionmaker = sessionmaker
        self._llm = llm
        self._embedding_service = embedding_service

    def start(self) -> None:
        """Start the background drain task (no-op if already running)."""
        if self.is_running:
            return
        if (
            self._sessionmaker is None
            or self._llm is None
            or self._embedding_service is None
        ):
            logger.warning("enrichment worker not configured; not starting")
            return
        self._task = asyncio.create_task(self._run())
        self.is_running = True
        logger.info("enrichment worker started")

    async def stop(self) -> None:
        """Stop the worker, cancelling the drain task."""
        self.is_running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("enrichment worker stopped")

    def enqueue(self, conversation_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Queue a committed turn for enrichment. No-op when the worker is idle."""
        if not self.is_running:
            return
        self._queue.put_nowait(
            EnrichmentJob(conversation_id=conversation_id, user_id=user_id)
        )

    def status(self) -> dict[str, object]:
        """Runtime snapshot for the health probe."""
        return {
            "running": self.is_running,
            "configured": self._sessionmaker is not None,
            "pending_jobs": self._queue.qsize(),
        }

    async def join(self) -> None:
        """Wait until all queued jobs are processed (used by tests)."""
        await self._queue.join()

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._process(job)
            finally:
                self._queue.task_done()

    async def _process(self, job: EnrichmentJob) -> None:
        assert self._sessionmaker is not None
        assert self._llm is not None
        assert self._embedding_service is not None
        # Publish the tenant for this background task so the per-transaction GUC
        # (app.current_user_id) is set and RLS lets each consumer read/write the
        # user's rows. The request path does this in get_current_user; a worker
        # task has no request, so we set it here. Cleared after the job so it
        # never leaks to the next one.
        set_current_user_id(job.user_id)
        try:
            # Each consumer in its own session/transaction → isolated failures.
            for consumer in ENRICHMENT_CONSUMERS:
                try:
                    async with self._sessionmaker() as session:
                        await consumer(session, job, self._llm, self._embedding_service)
                        await session.commit()
                except Exception as exc:
                    consumer_name = getattr(consumer, "__name__", str(consumer))
                    logger.warning(
                        "enrichment consumer %s failed for conversation %s: %s",
                        consumer_name,
                        job.conversation_id,
                        exc,
                    )
                    # Swallowed by design so one consumer's failure never blocks
                    # the others — captured to the local log so it isn't invisible.
                    # Covers memory-extraction failures (the extract_memories
                    # consumer) and every other background enrichment failure.
                    capture_exception(
                        exc,
                        component="enrichment_worker",
                        consumer=consumer_name,
                        conversation_id=str(job.conversation_id),
                    )
        finally:
            set_current_user_id(None)


# Module-level singleton wired up by the app lifespan.
enrichment_worker = EnrichmentWorker()
