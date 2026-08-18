"""Data access for automations and their runs (tenant-scoped, no business logic).

The one method worth reading is :func:`claim_run`. It is how the scheduler
guarantees a slot fires once: claiming is an INSERT into ``automation_runs``,
and the unique constraint on ``(automation_id, scheduled_for)`` turns a second
claim into an integrity error rather than a second reminder.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation import Automation, AutomationRun
from app.models.enums import (
    AutomationKind,
    AutomationRunStatus,
    AutomationSchedule,
    AutomationStatus,
)


async def create_automation(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    description: str | None,
    kind: AutomationKind,
    schedule: AutomationSchedule,
    next_run_at: datetime | None,
    timezone: str = "UTC",
    payload: dict | None = None,
) -> Automation:
    """Insert an automation. Caller commits."""
    automation = Automation(
        user_id=user_id,
        name=name,
        description=description,
        kind=kind,
        schedule=schedule,
        next_run_at=next_run_at,
        timezone=timezone,
        payload=payload,
    )
    session.add(automation)
    await session.flush()
    return automation


async def get_automation(
    session: AsyncSession, *, automation_id: uuid.UUID, user_id: uuid.UUID
) -> Automation | None:
    """One automation, tenant-scoped."""
    return await session.scalar(
        select(Automation).where(
            Automation.id == automation_id, Automation.user_id == user_id
        )
    )


async def list_automations(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Automation], int]:
    """A page of the user's automations (newest first) and the total."""
    total = await session.scalar(
        select(func.count())
        .select_from(Automation)
        .where(Automation.user_id == user_id)
    )
    rows = await session.scalars(
        select(Automation)
        .where(Automation.user_id == user_id)
        .order_by(Automation.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), int(total or 0)


async def list_due(
    session: AsyncSession, *, now: datetime, limit: int = 20
) -> list[Automation]:
    """Automations whose slot has arrived.

    Deliberately NOT tenant-scoped: the scheduler runs as the system, outside
    any request, so there is no acting user. It reads on the owner connection
    for the same reason authentication does. Everything it then does is scoped
    to the automation's own ``user_id``.
    """
    rows = await session.scalars(
        select(Automation)
        .where(
            Automation.enabled.is_(True),
            Automation.status == AutomationStatus.ACTIVE,
            Automation.next_run_at.is_not(None),
            Automation.next_run_at <= now,
        )
        .order_by(Automation.next_run_at)
        .limit(limit)
    )
    return list(rows)


async def claim_run(
    session: AsyncSession,
    *,
    automation: Automation,
    scheduled_for: datetime,
) -> AutomationRun | None:
    """Claim one slot, or return None when it is already claimed.

    A SAVEPOINT wraps the insert so a losing race rolls back only this
    statement — the caller's transaction survives and moves on to the next
    automation, rather than the whole scheduler tick dying on a duplicate.
    """
    run = AutomationRun(
        automation_id=automation.id,
        user_id=automation.user_id,
        scheduled_for=scheduled_for,
        status=AutomationRunStatus.RUNNING,
    )
    try:
        async with session.begin_nested():
            session.add(run)
            await session.flush()
    except IntegrityError:
        # Someone else already owns this slot. Not an error — the guarantee working.
        return None
    return run


async def finish_run(
    session: AsyncSession,
    run: AutomationRun,
    *,
    status: AutomationRunStatus,
    finished_at: datetime,
    output: str | None = None,
    error: str | None = None,
) -> AutomationRun:
    """Record how a run ended. Caller commits."""
    run.status = status
    run.finished_at = finished_at
    run.output = output
    run.error = error
    await session.flush()
    return run


async def list_runs(
    session: AsyncSession,
    *,
    automation_id: uuid.UUID,
    user_id: uuid.UUID,
    limit: int = 20,
) -> list[AutomationRun]:
    """An automation's recent runs, newest first (tenant-scoped)."""
    rows = await session.scalars(
        select(AutomationRun)
        .where(
            AutomationRun.automation_id == automation_id,
            AutomationRun.user_id == user_id,
        )
        .order_by(AutomationRun.scheduled_for.desc())
        .limit(limit)
    )
    return list(rows)


async def delete_automation(session: AsyncSession, automation: Automation) -> None:
    """Delete an automation and (by cascade) its runs. Caller commits."""
    await session.delete(automation)
    await session.flush()
