"""Lightweight in-process embedding worker.

A single asyncio task drains a queue of embedding jobs, each processed in its own
DB session with bounded exponential-backoff retries. Failures are logged and
dropped (never crash the worker). This keeps embeddings fresh without blocking the
request path and without external infrastructure (Redis/Celery) in Phase 1.

A module-level ``embedding_worker`` singleton is enqueued to by the memory service
on create/update, and started/stopped by the app lifespan.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.constants import (
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_RETRY_BASE_DELAY_SECONDS,
)
from app.repositories import memory_repository as repo
from app.services.embeddings.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingJob:
    memory_id: uuid.UUID
    user_id: uuid.UUID


class EmbeddingWorker:
    """Consumes embedding jobs from an in-memory queue."""

    def __init__(
        self,
        *,
        max_retries: int = EMBEDDING_MAX_RETRIES,
        retry_base_delay: float = EMBEDDING_RETRY_BASE_DELAY_SECONDS,
    ) -> None:
        self._queue: asyncio.Queue[EmbeddingJob] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None
        self._embedding_service: EmbeddingService | None = None
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self.is_running = False

    def configure(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        embedding_service: EmbeddingService,
    ) -> None:
        """Inject runtime dependencies (called from the app lifespan/tests)."""
        self._sessionmaker = sessionmaker
        self._embedding_service = embedding_service

    def start(self) -> None:
        """Start the background drain task (no-op if already running)."""
        if self.is_running:
            return
        if self._sessionmaker is None or self._embedding_service is None:
            logger.warning("embedding worker not configured; not starting")
            return
        self._task = asyncio.create_task(self._run())
        self.is_running = True
        logger.info("embedding worker started")

    async def stop(self) -> None:
        """Stop the worker, cancelling the drain task."""
        self.is_running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("embedding worker stopped")

    def enqueue(self, memory_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Queue a memory for (re)embedding. No-op when the worker is idle."""
        if not self.is_running:
            return
        self._queue.put_nowait(EmbeddingJob(memory_id=memory_id, user_id=user_id))

    async def join(self) -> None:
        """Wait until all queued jobs are processed (used by tests)."""
        await self._queue.join()

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._process_with_retries(job)
            finally:
                self._queue.task_done()

    async def _process_with_retries(self, job: EmbeddingJob) -> None:
        for attempt in range(1, self._max_retries + 1):
            try:
                await self._process(job)
                return
            except Exception as exc:
                logger.warning(
                    "embedding job failed (attempt %d/%d) for memory %s: %s",
                    attempt,
                    self._max_retries,
                    job.memory_id,
                    exc,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_base_delay * (2 ** (attempt - 1)))
        logger.error("embedding job permanently failed for memory %s", job.memory_id)

    async def _process(self, job: EmbeddingJob) -> None:
        assert self._sessionmaker is not None
        assert self._embedding_service is not None
        async with self._sessionmaker() as session:
            memory = await repo.get_memory(
                session, memory_id=job.memory_id, user_id=job.user_id
            )
            if memory is None:
                return
            await self._embedding_service.sync_memory_embedding(session, memory=memory)
            await session.commit()


# Module-level singleton wired up by the app lifespan.
embedding_worker = EmbeddingWorker()
