"""The automation scheduler — a poller over a durable table.

Structurally unlike ``embedding_worker`` and ``enrichment_worker``, and
deliberately so. Those drain an in-memory queue, which is fine for work that is
re-derivable from committed data: lose an embedding job and the next retrieval
still works, or a reconciliation pass can rebuild it.

A reminder is not re-derivable. If "remind me tomorrow at 9" lives only in a
process's memory, a restart loses it silently — no error, no record, and the
user simply never hears from GUMMY again about the thing they asked for. So the
schedule lives in Postgres and this worker only *reads* it. Nothing is queued in
memory; a restart re-reads the table and continues.

The poll interval is the resolution of the whole system: a task due at 09:00
fires within one interval of it. 30s is chosen for reminders, which are the
common case and where a minute of drift is invisible. It is not a cron
replacement and does not pretend to be.

Duplicate execution is prevented in the database, not here — claiming a slot is
an INSERT against a unique constraint (see ``automation_repository.claim_run``),
so two schedulers racing produce one run and one integrity error.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.observability import capture_exception
from app.services.automation import automation_service

logger = logging.getLogger(__name__)

# How often the table is checked. Also the worst-case lateness of any task.
DEFAULT_POLL_SECONDS = 30.0


class AutomationScheduler:
    """Polls the automations table and fires whatever is due."""

    def __init__(self, *, poll_seconds: float = DEFAULT_POLL_SECONDS) -> None:
        self._task: asyncio.Task[None] | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None
        self._poll_seconds = poll_seconds
        self.is_running = False
        self.ticks = 0
        self.runs_executed = 0

    def configure(
        self, *, sessionmaker: async_sessionmaker[AsyncSession] | None
    ) -> None:
        self._sessionmaker = sessionmaker

    def start(self) -> None:
        """Begin polling. No-op without a database, as in the other workers."""
        if self._sessionmaker is None:
            logger.info("automation scheduler idle (no database configured)")
            return
        if self._task is not None and not self._task.done():
            return
        self.is_running = True
        self._task = asyncio.create_task(self._run())
        logger.info("automation scheduler started (poll=%.0fs)", self._poll_seconds)

    async def stop(self) -> None:
        self.is_running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("automation scheduler stopped")

    def status(self) -> dict[str, object]:
        return {
            "running": self.is_running,
            "poll_seconds": self._poll_seconds,
            "ticks": self.ticks,
            "runs_executed": self.runs_executed,
        }

    async def _run(self) -> None:
        # A first tick immediately on startup, before the first sleep: this is
        # the restart-recovery path. Anything that came due while the process
        # was down is already in the table and fires now rather than after a
        # full interval.
        while self.is_running:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # The loop must outlive any single failure — a scheduler that
                # dies on one bad row stops every future task silently.
                logger.exception("automation scheduler tick failed")
                capture_exception(exc, component="automation_scheduler")
            try:
                await asyncio.sleep(self._poll_seconds)
            except asyncio.CancelledError:
                raise

    async def tick(self, *, now: datetime | None = None) -> int:
        """Run one pass. Returns how many automations fired.

        Exposed so tests can drive the scheduler deterministically instead of
        waiting on wall-clock time.
        """
        if self._sessionmaker is None:
            return 0
        moment = now or datetime.now(UTC)
        self.ticks += 1
        async with self._sessionmaker() as session:
            executed = await automation_service.run_due(session, now=moment)
        self.runs_executed += len(executed)
        if executed:
            logger.info("automation scheduler fired %d task(s)", len(executed))
        return len(executed)


# Module-level singleton, started/stopped by the app lifespan.
automation_scheduler = AutomationScheduler()
