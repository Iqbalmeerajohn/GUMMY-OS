"""Green tools: create and inspect the user's scheduled automations.

Creating a reminder is a *write*, which makes this the first non-read-only
capability in the catalog. It stays GREEN deliberately: the effect is confined
to GUMMY's own database, it is visible in the Automations panel, it is trivially
reversible by deleting the row, and it reaches nothing outside the machine.
That is the same standard the other GREEN tools meet. Anything that leaves the
box — email, calendar — is YELLOW and still has no executor.

The scheduling grammar the model can express is deliberately narrow: a time, and
one of once/daily/weekly. Free-form cron would let a small model invent
schedules nobody asked for, and every value here has an executor behind it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.enums import AutomationKind, AutomationSchedule
from app.services.agents.tools.context import ToolContext
from app.services.automation import automation_service

_MAX_ACTIVE_PER_USER = 50


class AutomationArgumentError(ValueError):
    """The model asked for a schedule that cannot be honoured."""


def parse_when(value: str, *, now: datetime) -> datetime:
    """Turn the model's ``when`` into an absolute UTC instant.

    Accepts an ISO-8601 timestamp (what the tool asks for) and a small set of
    phrasings models reach for anyway — "tomorrow 09:00", "in 2 hours". Being
    liberal here costs a few lines; being strict costs the user their reminder,
    because a rejected call usually ends with the model apologising rather than
    retrying in the right format.
    """
    raw = value.strip()
    if not raw:
        raise AutomationArgumentError("a time is required")

    # ISO-8601 first: the documented contract.
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        pass

    lowered = raw.lower()

    # "in 2 hours" / "in 30 minutes" / "in 3 days"
    if lowered.startswith("in "):
        parts = lowered.split()
        if len(parts) >= 3 and parts[1].isdigit():
            amount = int(parts[1])
            unit = parts[2].rstrip("s")
            deltas = {
                "minute": timedelta(minutes=amount),
                "hour": timedelta(hours=amount),
                "day": timedelta(days=amount),
                "week": timedelta(weeks=amount),
            }
            if unit in deltas:
                return now + deltas[unit]

    # "tomorrow 09:00" / "today 17:30"
    for word, offset in (("tomorrow", 1), ("today", 0)):
        if lowered.startswith(word):
            rest = lowered[len(word) :].strip().replace("at", "").strip()
            hour, minute = 9, 0
            if rest:
                bits = rest.split(":")
                try:
                    hour = int(bits[0])
                    minute = int(bits[1]) if len(bits) > 1 else 0
                except ValueError as exc:
                    raise AutomationArgumentError(
                        f"could not read a time from {raw!r}"
                    ) from exc
            target = (now + timedelta(days=offset)).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            return target

    raise AutomationArgumentError(
        f"could not read {raw!r} as a time. Use an ISO-8601 timestamp "
        "such as 2026-08-19T09:00:00Z."
    )


async def execute_create(context: ToolContext, args: dict) -> dict:
    """Create a scheduled automation for the calling user."""
    name = str(args.get("name", "")).strip()
    if not name:
        raise AutomationArgumentError("automation_create requires a 'name'")

    when_raw = str(args.get("when", "")).strip()
    now = datetime.now(UTC)
    run_at = parse_when(when_raw, now=now)
    if run_at <= now:
        # A time already past would fire instantly, which is never what the
        # user meant by "remind me".
        raise AutomationArgumentError(
            f"{when_raw!r} is in the past; pick a future time."
        )

    schedule_raw = str(args.get("schedule", "once")).strip().lower()
    try:
        schedule = AutomationSchedule(schedule_raw)
    except ValueError as exc:
        raise AutomationArgumentError(
            f"schedule must be one of: "
            f"{', '.join(s.value for s in AutomationSchedule)}"
        ) from exc

    kind_raw = str(args.get("kind", "reminder")).strip().lower()
    try:
        kind = AutomationKind(kind_raw)
    except ValueError as exc:
        raise AutomationArgumentError(
            f"kind must be one of: {', '.join(k.value for k in AutomationKind)}"
        ) from exc

    existing, total = await automation_service.list_for_user(
        context.session, user_id=context.user_id, limit=1, offset=0
    )
    if total >= _MAX_ACTIVE_PER_USER:
        raise AutomationArgumentError(
            f"You already have {total} automations, which is the limit. "
            "Delete one before adding another."
        )

    note = str(args.get("message", "")).strip() or name
    automation = await automation_service.create(
        context.session,
        user_id=context.user_id,
        name=name,
        description=note,
        kind=kind,
        schedule=schedule,
        run_at=run_at,
        payload={"message": note},
    )
    return {
        "created": True,
        "id": str(automation.id),
        "name": automation.name,
        "kind": automation.kind.value,
        "schedule": automation.schedule.value,
        "next_run_at": (
            automation.next_run_at.isoformat() if automation.next_run_at else None
        ),
        # So the reply can be truthful about what actually happens next.
        "note": (
            "Saved. It will appear in the Automations panel and fire at the "
            "scheduled time inside GUMMY. It does not send email or create "
            "calendar events."
        ),
    }


async def execute_list(context: ToolContext, args: dict) -> dict:
    """List the user's automations."""
    items, total = await automation_service.list_for_user(
        context.session, user_id=context.user_id, limit=50, offset=0
    )
    return {
        "total": total,
        "automations": [
            {
                "id": str(a.id),
                "name": a.name,
                "kind": a.kind.value,
                "schedule": a.schedule.value,
                "status": a.status.value,
                "enabled": a.enabled,
                "next_run_at": a.next_run_at.isoformat() if a.next_run_at else None,
                "last_run_at": a.last_run_at.isoformat() if a.last_run_at else None,
            }
            for a in items
        ],
    }
