"""Automation service — lifecycle, scheduling arithmetic, and execution.

The scheduling arithmetic is pure (``next_occurrence``) so it can be tested
against fixed instants rather than against the wall clock. Everything with a
side effect takes ``now`` as an argument for the same reason.

One rule shapes the rest: **an automation never claims to have done something it
did not do.** A reminder produces a message the user can see; it does not send
an email, and it does not say it did.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.automation import Automation, AutomationRun
from app.models.enums import (
    AutomationKind,
    AutomationRunStatus,
    AutomationSchedule,
    AutomationStatus,
)
from app.repositories import automation_repository as repo

logger = logging.getLogger(__name__)

# Consecutive failures before an automation is parked. An endlessly-retrying
# reminder is noise, not resilience; parking it makes the problem visible in
# the UI instead of burying it in a log.
MAX_CONSECUTIVE_FAILURES = 3

# How many automations one scheduler tick will run. Bounds the work a single
# tick can do so a backlog drains steadily instead of stalling the loop.
SCHEDULER_BATCH_SIZE = 20


class AutomationNotFoundError(AppError):
    """No such automation for this tenant."""

    def __init__(self, automation_id: uuid.UUID) -> None:
        super().__init__(
            f"Automation {automation_id} not found.",
            code="automation_not_found",
            status_code=404,
        )


def _utc(moment: datetime) -> datetime:
    """Treat a naive datetime as UTC.

    Timestamps written with a timezone come back without one on backends that
    do not store the offset (SQLite, which the fast test suite uses). Comparing
    a naive value against an aware one raises, so every stored instant is
    normalized on the way in. The same defensive helper exists in the memory
    retrieval service, for the same reason.
    """
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


# ── Scheduling arithmetic (pure) ─────────────────────────────────────────────


def next_occurrence(
    schedule: AutomationSchedule, *, after: datetime, anchor: datetime
) -> datetime | None:
    """The next time a schedule fires strictly after ``after``.

    ``anchor`` is the automation's original run time, which fixes the time of
    day and the weekday. Stepping forward from the anchor rather than from
    "now" is what stops a daily 9am reminder drifting later every time the
    machine is asleep at 9 and the run happens at 9:40.

    Returns None for a one-off schedule, which has no next occurrence.
    """
    if schedule is AutomationSchedule.ONCE:
        return None

    after = _utc(after)
    step = timedelta(days=1 if schedule is AutomationSchedule.DAILY else 7)
    nxt = _utc(anchor)
    if nxt <= after:
        # Jump directly to the first slot after ``after`` rather than looping
        # one step at a time: an automation dormant for a year would otherwise
        # spin through 365 iterations to catch up.
        missed = ((after - nxt) // step) + 1
        nxt = nxt + step * missed
    return nxt


# ── Lifecycle ────────────────────────────────────────────────────────────────


async def create(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    kind: AutomationKind,
    schedule: AutomationSchedule,
    run_at: datetime,
    description: str | None = None,
    timezone: str = "UTC",
    payload: dict | None = None,
) -> Automation:
    """Create an automation scheduled for ``run_at``. Commits."""
    automation = await repo.create_automation(
        session,
        user_id=user_id,
        name=name.strip()[:200],
        description=description,
        kind=kind,
        schedule=schedule,
        next_run_at=run_at,
        timezone=timezone,
        payload=payload,
    )
    await session.commit()
    await session.refresh(automation)
    logger.info(
        "automation created: kind=%s schedule=%s next_run_at=%s",
        kind.value,
        schedule.value,
        run_at.isoformat(),
    )
    return automation


async def get(
    session: AsyncSession, *, user_id: uuid.UUID, automation_id: uuid.UUID
) -> Automation:
    """One automation, or 404."""
    automation = await repo.get_automation(
        session, automation_id=automation_id, user_id=user_id
    )
    if automation is None:
        raise AutomationNotFoundError(automation_id)
    return automation


async def list_for_user(
    session: AsyncSession, *, user_id: uuid.UUID, limit: int = 100, offset: int = 0
) -> tuple[list[Automation], int]:
    return await repo.list_automations(
        session, user_id=user_id, limit=limit, offset=offset
    )


async def set_enabled(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    automation_id: uuid.UUID,
    enabled: bool,
    now: datetime | None = None,
) -> Automation:
    """Pause or resume. Resuming re-anchors a missed slot to the next real one.

    Without that, resuming an automation that was paused past its due time fires
    immediately — which reads as a bug to the user, not as catch-up.
    """
    now = now or datetime.now(UTC)
    automation = await get(session, user_id=user_id, automation_id=automation_id)
    automation.enabled = enabled
    automation.status = AutomationStatus.ACTIVE if enabled else AutomationStatus.PAUSED
    if enabled:
        automation.failure_count = 0
        automation.last_error = None
        if automation.next_run_at is not None and _utc(automation.next_run_at) <= now:
            automation.next_run_at = next_occurrence(
                automation.schedule, after=now, anchor=automation.next_run_at
            )
            if automation.next_run_at is None:
                # A one-off whose moment passed while paused cannot be revived.
                automation.status = AutomationStatus.COMPLETED
    await session.commit()
    await session.refresh(automation)
    return automation


async def delete(
    session: AsyncSession, *, user_id: uuid.UUID, automation_id: uuid.UUID
) -> None:
    automation = await get(session, user_id=user_id, automation_id=automation_id)
    await repo.delete_automation(session, automation)
    await session.commit()


# ── Execution ────────────────────────────────────────────────────────────────


def render(automation: Automation) -> str:
    """The message an automation produces when it fires.

    Deliberately plain text produced locally. Delivering it anywhere — email,
    push, calendar — needs a connector that does not exist, and an automation
    that claimed to have emailed the user would be lying.
    """
    payload = automation.payload if isinstance(automation.payload, dict) else {}
    if automation.kind is AutomationKind.REMINDER:
        note = str(payload.get("message") or automation.description or automation.name)
        return f"Reminder: {note}"
    if automation.kind is AutomationKind.GOAL_CHECK_IN:
        return (
            f"Goal check-in: {automation.name}. "
            "Worth a look at where this stands and what the next small step is."
        )
    return f"{automation.name}: your scheduled summary is ready."


async def run_once(
    session: AsyncSession, automation: Automation, *, now: datetime
) -> AutomationRun | None:
    """Fire one due slot, or return None when another worker owns it.

    Advancing the schedule happens whether the body succeeded or failed: a
    reminder that errored should still move to tomorrow rather than retry in a
    tight loop against whatever broke it.
    """
    slot = _utc(automation.next_run_at) if automation.next_run_at else now
    run = await repo.claim_run(session, automation=automation, scheduled_for=slot)
    if run is None:
        logger.debug("automation %s slot %s already claimed", automation.id, slot)
        return None

    try:
        output = render(automation)
        await repo.finish_run(
            session,
            run,
            status=AutomationRunStatus.SUCCEEDED,
            finished_at=now,
            output=output,
        )
        automation.failure_count = 0
        automation.last_error = None
    except Exception as exc:
        logger.exception("automation %s failed", automation.id)
        await repo.finish_run(
            session,
            run,
            status=AutomationRunStatus.FAILED,
            finished_at=now,
            error=str(exc)[:500],
        )
        automation.failure_count += 1
        automation.last_error = str(exc)[:500]
        if automation.failure_count >= MAX_CONSECUTIVE_FAILURES:
            automation.status = AutomationStatus.FAILED
            automation.enabled = False

    automation.last_run_at = now
    nxt = next_occurrence(automation.schedule, after=now, anchor=slot)
    automation.next_run_at = nxt
    if nxt is None and automation.status is AutomationStatus.ACTIVE:
        automation.status = AutomationStatus.COMPLETED
        automation.enabled = False

    await session.commit()
    return run


async def run_due(
    session: AsyncSession, *, now: datetime, limit: int = SCHEDULER_BATCH_SIZE
) -> list[AutomationRun]:
    """Fire everything whose slot has arrived. Returns the runs that executed.

    One automation's failure never stops the batch: each is independent, and a
    single bad payload must not prevent every other reminder from arriving.
    """
    due = await repo.list_due(session, now=now, limit=limit)
    executed: list[AutomationRun] = []
    for automation in due:
        try:
            run = await run_once(session, automation, now=now)
            if run is not None:
                executed.append(run)
        except Exception:
            logger.exception("automation %s could not be processed", automation.id)
            await session.rollback()
    return executed
