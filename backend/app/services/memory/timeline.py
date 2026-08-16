"""Episodic timeline — *when* things happened, not just that they did.

Semantic memory answers "where do I live". It cannot answer "what did I do last
week", because nothing in a fact says when the thing occurred: a note written
today about last Tuesday sorts as today, and similarity search over "last week"
matches nothing meaningful. The fix is one nullable column, ``occurred_at``, and
two small pieces of logic around it:

* :func:`parse_occurred_at` reads the everyday time phrases people actually use
  ("yesterday", "last Tuesday", "3 days ago") off an extracted fact and anchors
  it in time. Null stays the common case — most facts are not events.
* :func:`detect_window` recognises the retrospective *question* and turns it
  into a date range, which is a cheap indexed read rather than a retrieval guess.

Both are regex-based and past-facing only. Future phrases ("next Friday") are
deliberately ignored: those are goals, and goals already have their own model.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.repositories import memory_repository as memory_repo

# How many events a retrospective answer may cite. Beyond this the reply stops
# being a recollection and becomes a log dump.
TIMELINE_LIMIT = 12

_WEEKDAYS: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_UNIT_DAYS: dict[str, float] = {
    "day": 1,
    "week": 7,
    "month": 30,
    "year": 365,
}

_AGO = re.compile(r"\b(\d{1,3})\s+(day|week|month|year)s?\s+ago\b")
_LAST_UNIT = re.compile(r"\blast\s+(day|week|month|year)\b")
_WEEKDAY = re.compile(
    r"\b(?:last|on|this\s+past)\s+"
    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b"
)


def _now() -> datetime:
    return datetime.now(UTC)


def parse_occurred_at(text: str, *, now: datetime | None = None) -> datetime | None:
    """Anchor an extracted fact in time, or return None if it is not an event.

    Resolution is a day, not a second — "yesterday" is honest to within a day and
    pretending otherwise would invent precision the source text never had.
    """
    reference = now or _now()
    lowered = text.lower()

    match = _AGO.search(lowered)
    if match:
        amount = int(match.group(1))
        return reference - timedelta(days=amount * _UNIT_DAYS[match.group(2)])

    match = _WEEKDAY.search(lowered)
    if match:
        target = _WEEKDAYS[match.group(1)]
        # Days back to the most recent past occurrence; a weekday named today
        # means the one a week ago, since the phrasing is retrospective.
        delta = (reference.weekday() - target) % 7 or 7
        return reference - timedelta(days=delta)

    match = _LAST_UNIT.search(lowered)
    if match:
        return reference - timedelta(days=_UNIT_DAYS[match.group(1)])

    if re.search(r"\blast night\b", lowered):
        return reference - timedelta(hours=12)
    if re.search(r"\byesterday\b", lowered):
        return reference - timedelta(days=1)
    if re.search(r"\b(today|this morning|this afternoon|tonight)\b", lowered):
        return reference
    return None


@dataclass(frozen=True)
class Window:
    """A closed-open time range a retrospective question is asking about."""

    label: str
    start: datetime
    end: datetime


# The question has to be *retrospective*, not merely contain a date word.
# "Ship this by Friday" mentions a day; "what did I do on Friday" asks the
# timeline. Requiring one of these cues is what keeps the two apart.
_RETROSPECTIVE = re.compile(
    r"\b(what (did|have) i|what happened|what was i|remind me what|"
    r"recap|catch me up|summar(y|ise|ize) of my|did i (do|finish|ship|say))\b"
)

_WINDOWS: tuple[tuple[str, str, float], ...] = (
    # (label, pattern, days back)
    ("yesterday", r"\byesterday\b", 1),
    ("today", r"\b(today|so far today|this morning)\b", 1),
    ("this week", r"\b(this week|past week|last week|last 7 days)\b", 7),
    ("this month", r"\b(this month|past month|last month|last 30 days)\b", 30),
    ("recently", r"\b(recently|lately|these days)\b", 14),
)


def detect_window(question: str, *, now: datetime | None = None) -> Window | None:
    """Turn a retrospective question into a date range, or None."""
    reference = now or _now()
    lowered = question.lower()
    if not _RETROSPECTIVE.search(lowered):
        return None
    for label, pattern, days in _WINDOWS:
        if re.search(pattern, lowered):
            if label == "yesterday":
                start = reference - timedelta(days=2)
                end = reference - timedelta(days=1)
            else:
                start = reference - timedelta(days=days)
                end = reference + timedelta(days=1)
            return Window(label=label, start=start, end=end)
    return None


async def events(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    window: Window,
    limit: int = TIMELINE_LIMIT,
) -> list[Memory]:
    """Time-anchored memories inside the window, newest first."""
    return await memory_repo.list_events(
        session,
        user_id=user_id,
        since=window.start,
        until=window.end,
        limit=limit,
    )


def render(window: Window, memories: list[Memory]) -> str | None:
    """The prompt block for a retrospective question, or None when empty.

    Empty is worth returning as None: an explicit "nothing recorded" block reads
    to the model as a fact about the user's week, when it is really a fact about
    what was written down.
    """
    if not memories:
        return None
    lines = [
        f"- {m.occurred_at:%Y-%m-%d}: {m.content}"
        for m in memories
        if m.occurred_at is not None
    ]
    if not lines:
        return None
    body = "\n".join(lines)
    return (
        f"What the user did during {window.label} (use this to answer their "
        f"retrospective question; it is the complete record you have):\n"
        f"<timeline>\n{body}\n</timeline>"
    )
