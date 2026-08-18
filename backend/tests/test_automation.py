"""Automation: durability, idempotency, isolation, and honesty.

The interesting properties here are the ones a naive scheduler gets wrong.

A reminder is not re-derivable work. If it lives only in a process's memory, a
restart loses it with no error and no record — the user simply never hears from
GUMMY again about the thing they asked for. So the schedule is a table, and the
tests below drive the scheduler deterministically against fixed instants rather
than waiting on the wall clock.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    AutomationKind,
    AutomationRunStatus,
    AutomationSchedule,
    AutomationStatus,
)
from app.repositories import automation_repository as repo
from app.services.agents.tools import catalog, executor
from app.services.agents.tools.automation_tools import (
    AutomationArgumentError,
    parse_when,
)
from app.services.agents.tools.context import ToolContext
from app.services.agents.tools.executor import ToolOutcome
from app.services.automation import automation_service
from app.services.automation.automation_service import next_occurrence
from app.workers.automation_scheduler import AutomationScheduler

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def utc(moment: datetime | None) -> datetime | None:
    """Normalize a stored instant for comparison.

    SQLite (the fast suite's backend) does not persist the offset, so a value
    written as aware comes back naive. Postgres returns it aware. Normalizing
    here keeps the assertions about scheduling, not about storage.
    """
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


async def _make(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    run_at: datetime,
    schedule: AutomationSchedule = AutomationSchedule.ONCE,
    name: str = "Review goals",
):
    return await automation_service.create(
        session,
        user_id=user_id,
        name=name,
        kind=AutomationKind.REMINDER,
        schedule=schedule,
        run_at=run_at,
        payload={"message": name},
    )


# ── Scheduling arithmetic (pure) ─────────────────────────────────────────────


def test_a_one_off_has_no_next_occurrence() -> None:
    assert next_occurrence(AutomationSchedule.ONCE, after=NOW, anchor=NOW) is None


def test_daily_steps_by_a_day_from_the_anchor() -> None:
    anchor = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)
    nxt = next_occurrence(AutomationSchedule.DAILY, after=anchor, anchor=anchor)
    assert nxt == datetime(2026, 8, 19, 9, 0, tzinfo=UTC)


def test_weekly_steps_by_a_week() -> None:
    anchor = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)
    nxt = next_occurrence(AutomationSchedule.WEEKLY, after=anchor, anchor=anchor)
    assert nxt == datetime(2026, 8, 25, 9, 0, tzinfo=UTC)


def test_a_daily_reminder_does_not_drift_when_it_runs_late() -> None:
    """The next slot is fixed by the anchor, not by when the run happened.

    Stepping from "now" would push a 9am reminder to 9:40 the next day, then
    later again, until it drifted out of the morning entirely.
    """
    anchor = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)
    ran_late = datetime(2026, 8, 18, 9, 40, tzinfo=UTC)

    nxt = next_occurrence(AutomationSchedule.DAILY, after=ran_late, anchor=anchor)

    assert nxt == datetime(2026, 8, 19, 9, 0, tzinfo=UTC)


def test_a_long_dormant_schedule_catches_up_in_one_step() -> None:
    """A year asleep must not mean 365 loop iterations."""
    anchor = datetime(2025, 8, 18, 9, 0, tzinfo=UTC)
    after = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)

    nxt = next_occurrence(AutomationSchedule.DAILY, after=after, anchor=anchor)

    assert nxt is not None
    assert nxt > after
    assert nxt.hour == 9  # time of day preserved


# ── Persistence and lifecycle ────────────────────────────────────────────────


async def test_created_automation_persists(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    automation = await _make(db_session, seed_user, run_at=NOW + timedelta(hours=1))

    found = await repo.get_automation(
        db_session, automation_id=automation.id, user_id=seed_user
    )
    assert found is not None
    assert found.status is AutomationStatus.ACTIVE
    assert utc(found.next_run_at) == NOW + timedelta(hours=1)


async def test_pause_and_resume(db_session: AsyncSession, seed_user: uuid.UUID) -> None:
    automation = await _make(db_session, seed_user, run_at=NOW + timedelta(hours=1))

    paused = await automation_service.set_enabled(
        db_session,
        user_id=seed_user,
        automation_id=automation.id,
        enabled=False,
        now=NOW,
    )
    assert paused.status is AutomationStatus.PAUSED
    assert not paused.enabled

    # ``now`` is pinned to the fixture clock: with the wall clock, the slot an
    # hour after NOW is already in the past and resume would correctly retire
    # this one-off as completed.
    resumed = await automation_service.set_enabled(
        db_session,
        user_id=seed_user,
        automation_id=automation.id,
        enabled=True,
        now=NOW,
    )
    assert resumed.status is AutomationStatus.ACTIVE
    assert resumed.enabled


async def test_resuming_past_its_slot_does_not_fire_immediately(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Otherwise un-pausing looks like a bug: the reminder arrives at once."""
    automation = await _make(
        db_session,
        seed_user,
        run_at=NOW + timedelta(hours=1),
        schedule=AutomationSchedule.DAILY,
    )
    await automation_service.set_enabled(
        db_session,
        user_id=seed_user,
        automation_id=automation.id,
        enabled=False,
        now=NOW,
    )

    much_later = NOW + timedelta(days=3)
    resumed = await automation_service.set_enabled(
        db_session,
        user_id=seed_user,
        automation_id=automation.id,
        enabled=True,
        now=much_later,
    )

    assert resumed.next_run_at is not None
    assert utc(resumed.next_run_at) > much_later


async def test_deleting_an_automation_removes_it(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    automation = await _make(db_session, seed_user, run_at=NOW + timedelta(hours=1))
    await automation_service.delete(
        db_session, user_id=seed_user, automation_id=automation.id
    )

    assert (
        await repo.get_automation(
            db_session, automation_id=automation.id, user_id=seed_user
        )
        is None
    )


# ── Execution ────────────────────────────────────────────────────────────────


async def test_a_due_automation_runs_and_records_output(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    automation = await _make(db_session, seed_user, run_at=NOW - timedelta(minutes=1))

    executed = await automation_service.run_due(db_session, now=NOW)

    assert len(executed) == 1
    assert executed[0].status is AutomationRunStatus.SUCCEEDED
    assert "Review goals" in (executed[0].output or "")
    await db_session.refresh(automation)
    assert utc(automation.last_run_at) == NOW


async def test_an_automation_not_yet_due_does_not_run(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    await _make(db_session, seed_user, run_at=NOW + timedelta(hours=2))

    assert await automation_service.run_due(db_session, now=NOW) == []


async def test_a_paused_automation_does_not_run(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    automation = await _make(db_session, seed_user, run_at=NOW - timedelta(minutes=1))
    await automation_service.set_enabled(
        db_session,
        user_id=seed_user,
        automation_id=automation.id,
        enabled=False,
        now=NOW,
    )

    assert await automation_service.run_due(db_session, now=NOW) == []


async def test_a_one_off_completes_after_firing(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    automation = await _make(db_session, seed_user, run_at=NOW - timedelta(minutes=1))

    await automation_service.run_due(db_session, now=NOW)
    await db_session.refresh(automation)

    assert automation.status is AutomationStatus.COMPLETED
    assert automation.next_run_at is None
    # And it does not fire again.
    assert (
        await automation_service.run_due(db_session, now=NOW + timedelta(days=1)) == []
    )


async def test_a_daily_automation_reschedules_itself(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    automation = await _make(
        db_session,
        seed_user,
        run_at=NOW - timedelta(minutes=1),
        schedule=AutomationSchedule.DAILY,
    )

    await automation_service.run_due(db_session, now=NOW)
    await db_session.refresh(automation)

    assert automation.status is AutomationStatus.ACTIVE
    assert automation.next_run_at is not None
    assert utc(automation.next_run_at) > NOW


# ── Idempotency: the property that stops duplicate reminders ────────────────


async def test_a_slot_fires_exactly_once(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Claiming a slot is an INSERT against a unique constraint.

    Two scheduler passes over the same due window — a race, a restart replaying,
    or a clock stepping backwards — must produce one reminder, not two.
    """
    automation = await _make(db_session, seed_user, run_at=NOW - timedelta(minutes=1))
    slot = automation.next_run_at
    assert slot is not None

    first = await repo.claim_run(db_session, automation=automation, scheduled_for=slot)
    second = await repo.claim_run(db_session, automation=automation, scheduled_for=slot)

    assert first is not None
    assert second is None, "the second claim must lose"


async def test_a_losing_claim_does_not_poison_the_session(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """A SAVEPOINT contains the integrity error, so the batch continues."""
    automation = await _make(db_session, seed_user, run_at=NOW - timedelta(minutes=1))
    slot = automation.next_run_at
    assert slot is not None

    await repo.claim_run(db_session, automation=automation, scheduled_for=slot)
    await repo.claim_run(db_session, automation=automation, scheduled_for=slot)

    # The session is still usable after the losing claim.
    items, total = await automation_service.list_for_user(db_session, user_id=seed_user)
    assert total == 1
    assert items[0].id == automation.id


async def test_running_the_same_due_window_twice_yields_one_run(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    automation = await _make(
        db_session,
        seed_user,
        run_at=NOW - timedelta(minutes=1),
        schedule=AutomationSchedule.DAILY,
    )

    first = await automation_service.run_due(db_session, now=NOW)
    second = await automation_service.run_due(db_session, now=NOW)

    assert len(first) == 1
    assert second == []
    runs = await repo.list_runs(
        db_session, automation_id=automation.id, user_id=seed_user
    )
    assert len(runs) == 1


# ── Restart recovery ─────────────────────────────────────────────────────────


async def test_a_schedule_survives_a_restart(
    db_session: AsyncSession, seed_user: uuid.UUID, sessionmaker_fixture
) -> None:
    """The durability property, stated directly.

    A fresh scheduler instance — the equivalent of a restarted process, holding
    no in-memory state — finds and fires work created before it existed.
    """
    await _make(db_session, seed_user, run_at=NOW - timedelta(minutes=1))

    restarted = AutomationScheduler()
    restarted.configure(sessionmaker=sessionmaker_fixture)
    fired = await restarted.tick(now=NOW)

    assert fired == 1
    assert restarted.runs_executed == 1


async def test_a_scheduler_with_no_database_is_inert(
    seed_user: uuid.UUID,
) -> None:
    scheduler = AutomationScheduler()
    scheduler.configure(sessionmaker=None)
    scheduler.start()

    assert await scheduler.tick(now=NOW) == 0
    await scheduler.stop()


# ── Tenant isolation ─────────────────────────────────────────────────────────


async def test_one_user_cannot_read_anothers_automation(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    automation = await _make(db_session, seed_user, run_at=NOW + timedelta(hours=1))
    other = uuid.uuid4()

    assert (
        await repo.get_automation(
            db_session, automation_id=automation.id, user_id=other
        )
        is None
    )


async def test_listing_is_scoped_to_the_caller(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    await _make(db_session, seed_user, run_at=NOW + timedelta(hours=1))

    _items, total = await automation_service.list_for_user(
        db_session, user_id=uuid.uuid4()
    )
    assert total == 0


# ── The tool the agent actually calls ────────────────────────────────────────


def _spec(key: str) -> catalog.ToolSpec:
    spec = catalog.get(key)
    assert spec is not None
    return spec


@pytest.mark.parametrize(
    ("phrase", "check"),
    [
        ("2026-08-19T09:00:00Z", lambda d: d.hour == 9 and d.day == 19),
        ("in 2 hours", lambda d: d.hour == 14),
        ("in 30 minutes", lambda d: d.minute == 30),
        ("tomorrow 09:00", lambda d: d.day == 19 and d.hour == 9),
        ("tomorrow", lambda d: d.day == 19 and d.hour == 9),
    ],
)
def test_parse_when_accepts_what_models_actually_emit(phrase: str, check) -> None:  # type: ignore[no-untyped-def]
    """Strictness here costs the user their reminder, not just a retry."""
    assert check(parse_when(phrase, now=NOW))


def test_parse_when_rejects_nonsense() -> None:
    with pytest.raises(AutomationArgumentError):
        parse_when("whenever you feel like it", now=NOW)


async def test_automation_create_tool_persists_a_real_row(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """The agent's claim must correspond to a row the user can see."""
    ctx = ToolContext(session=db_session, user_id=seed_user)
    result = await executor.run(
        _spec("automation_create"),
        ctx,
        {
            "name": "Review goals",
            "when": "in 2 hours",
            "schedule": "daily",
            "message": "Check goal progress",
        },
    )

    assert result.outcome is ToolOutcome.SUCCESS
    assert result.output is not None
    assert result.output["created"] is True

    _items, total = await automation_service.list_for_user(
        db_session, user_id=seed_user
    )
    assert total == 1


async def test_automation_create_refuses_a_past_time(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    ctx = ToolContext(session=db_session, user_id=seed_user)
    result = await executor.run(
        _spec("automation_create"),
        ctx,
        {"name": "x", "when": "2020-01-01T00:00:00Z"},
    )

    assert result.outcome is ToolOutcome.FAILED
    assert "past" in (result.error or "").lower()


async def test_automation_create_says_it_does_not_send_email(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """The tool's own output tells the model what it did NOT do.

    Left to itself a model will happily confirm "I've emailed you a reminder",
    because that is what the phrasing of the request implies.
    """
    ctx = ToolContext(session=db_session, user_id=seed_user)
    result = await executor.run(
        _spec("automation_create"), ctx, {"name": "x", "when": "in 1 hour"}
    )

    assert result.output is not None
    note = result.output["note"].lower()
    assert "does not send email" in note
    assert "calendar" in note


async def test_automation_list_tool_is_tenant_scoped(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    await _make(db_session, seed_user, run_at=NOW + timedelta(hours=1))

    mine = await executor.run(
        _spec("automation_list"),
        ToolContext(session=db_session, user_id=seed_user),
        {},
    )
    theirs = await executor.run(
        _spec("automation_list"),
        ToolContext(session=db_session, user_id=uuid.uuid4()),
        {},
    )

    assert mine.output is not None and mine.output["total"] == 1
    assert theirs.output is not None and theirs.output["total"] == 0


# ── Honesty ──────────────────────────────────────────────────────────────────


async def test_rendered_output_never_claims_an_external_action(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    automation = await _make(db_session, seed_user, run_at=NOW + timedelta(hours=1))

    rendered = automation_service.render(automation).lower()

    for claim in ("emailed", "sent you an email", "added to your calendar"):
        assert claim not in rendered


def test_the_persona_forbids_claiming_unconnected_actions() -> None:
    from app.services.agents.prompts import automation_agent_prompt

    persona = automation_agent_prompt.build_persona("", "").lower()
    assert "cannot send email" in persona
    assert "automation_create" in persona


def test_the_persona_carries_the_current_time() -> None:
    """A model has no clock.

    Found live: asked to remind the user "tomorrow at 9", the model computed
    the date from its training cutoff, called automation_create with a
    timestamp in the past, and the user got an apology instead of a reminder.
    ``current_time`` exists as a tool, but a chain of call-then-hold-then-
    compute has three places to fail on a small model. The fact is now simply
    present in the prompt before it is needed.
    """
    from datetime import datetime

    from app.services.agents.prompts import automation_agent_prompt

    persona = automation_agent_prompt.build_persona("", "")
    year = str(datetime.now(UTC).year)

    assert "Current date and time:" in persona
    assert year in persona
    assert "Never guess a date" in persona


def test_career_routing_covers_how_people_actually_phrase_it() -> None:
    """Found live: "fresher opportunities" matched no career keyword.

    The canonical nouns ("job", "resume") are not how the request usually
    arrives, and the keyword set has to span the capabilities the agent claims.
    """
    from app.services.agents.manifests import CAREER_AGENT

    keywords = set(CAREER_AGENT.keywords)
    for phrase in (
        "opportunities",
        "fresher",
        "scholarship",
        "certification",
        "hackathon",
        "exam",
        "placement",
    ):
        assert phrase in keywords, f"career should match {phrase!r}"
