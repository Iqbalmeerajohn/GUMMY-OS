"""Goal extraction — detect goal-like statements in a user message (M5.5).

Deterministic, LLM-free, and cheap: a small set of intent triggers plus a
hand-rolled date parser turn a sentence like *"I want to get an AI Engineer job
by July 2nd"* into a :class:`GoalCandidate`. There is **no LLM call** — detection
is a pure function over the message text, so it adds no latency or token cost to
a turn.

Detection NEVER creates a goal. The candidate is surfaced to the user for
explicit confirmation (the "Goal Detected" prompt), mirroring the
memory-consent philosophy already used across GUMMY: consent precedes
persistence. One best-effort Langfuse ``goal.extract`` span is emitted per call.
"""

from __future__ import annotations

import calendar
import re
from datetime import UTC, datetime, timedelta

from app.models.enums import GoalPriority
from app.observability import langfuse as langfuse_obs
from app.schemas.goal import GOAL_TITLE_MAX_LENGTH, GoalCandidate

# ── Intent triggers ───────────────────────────────────────────────────────────
# The phrasings that mark a durable objective (goal-system §M5.5). Anchored to
# the *start of a sentence* (begin-of-string or after sentence punctuation / a
# comma) so "do you want to…" or "you need to…" never match — only the user
# stating their OWN intent does. Longer phrases are listed first so the regex
# alternation prefers the most specific trigger (e.g. "i want to achieve" over
# "i want to").
_TRIGGERS: tuple[str, ...] = (
    "i want to achieve",
    "i want to",
    "i wanna",
    "i would like to",
    "i'd like to",
    "my goal is to",
    "my goal is",
    "i need to",
    "i have to",
    "i plan to",
    "i am planning to",
    "i'm planning to",
    "i am trying to",
    "i'm trying to",
    "i am aiming to",
    "i'm aiming to",
    "i aim to",
    "i hope to",
    "i intend to",
    "i am going to",
    "i'm going to",
)

# Built once: "(?:^|[.!?,]\s*)(trigger1|trigger2|…)\s+(.+)$", case-insensitive.
_TRIGGER_RE = re.compile(
    r"(?:^|[.!?,]\s*)(?:" + "|".join(re.escape(t) for t in _TRIGGERS) + r")\s+(.+)$",
    re.IGNORECASE,
)

# Objectives that read as transient questions, not durable goals. When the
# objective starts with one of these the candidate is rejected so "I want to
# know the weather" / "I need to ask you something" never become goals.
_WEAK_OBJECTIVE_VERBS: frozenset[str] = frozenset(
    {"know", "ask", "see", "hear", "understand", "remember", "tell", "check"}
)

# Priority signals (goal-system §M5.5). Urgency markers push HIGH; "someday"
# phrasings push LOW; a near-term target date also implies HIGH.
_HIGH_PRIORITY_MARKERS: tuple[str, ...] = (
    "urgent",
    "asap",
    "as soon as possible",
    "immediately",
    "right away",
    "critical",
    "this week",
    "by tomorrow",
)
_LOW_PRIORITY_MARKERS: tuple[str, ...] = (
    "someday",
    "eventually",
    "one day",
    "at some point",
    "no rush",
    "no hurry",
    "long term",
    "long-term",
    "whenever",
)
# A target date this close (or closer) is treated as HIGH priority on its own.
HIGH_PRIORITY_WINDOW_DAYS = 30

# ── Date parsing ──────────────────────────────────────────────────────────────
_MONTHS: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
# "<Month> <day>[, year]"  e.g. "July 2nd", "Jul 2, 2026"
_MONTH_DAY_RE = re.compile(
    rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?",
    re.IGNORECASE,
)
# "<day> <Month>[ year]"  e.g. "2nd July", "2 July 2026"
_DAY_MONTH_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_ALT})\b(?:,?\s+(\d{{4}}))?",
    re.IGNORECASE,
)
# Bare "<Month>" only when introduced by a temporal preposition, so the common
# word "may" doesn't get mistaken for the month in "I may apply".
_MONTH_ONLY_RE = re.compile(
    rf"\b(?:by|in|before|on|around|until|till|til|due)\s+({_MONTH_ALT})\b",
    re.IGNORECASE,
)
_IN_N_UNITS_RE = re.compile(
    r"\bin\s+(\d{1,3})\s+(day|days|week|weeks|month|months)\b", re.IGNORECASE
)

# Trailing temporal clause to strip off the title (after the date is parsed from
# the full message): "… by July 2nd", "… this year", "… in 3 weeks".
_TRAILING_DATE_CLAUSE_RE = re.compile(
    r"\s+(?:"
    r"(?:by|before|until|till|til|around|due(?:\s+by)?|on|in)\s+.+"
    r"|(?:this|next)\s+(?:year|month|week)\b.*"
    r"|by\s+the\s+end\s+of\b.*"
    r")$",
    re.IGNORECASE,
)


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _build_month_date(
    month: int, day: int, year_str: str | None, now: datetime
) -> datetime | None:
    """Assemble a UTC date from a parsed month/day, inferring the year.

    Without an explicit year, the next future occurrence is chosen: if the
    month/day has already passed this year, it rolls to next year. An invalid
    day for the month (e.g. Feb 30) yields ``None``.
    """
    try:
        if year_str:
            return datetime(int(year_str), month, day, tzinfo=UTC)
        candidate = datetime(now.year, month, day, tzinfo=UTC)
        if candidate.date() < now.date():
            candidate = datetime(now.year + 1, month, day, tzinfo=UTC)
        return candidate
    except ValueError:
        return None


def _parse_relative_date(lowered: str, now: datetime) -> datetime | None:
    """Parse relative phrasings ("this year", "next month", "in 3 weeks")."""
    if (
        "this year" in lowered
        or "end of the year" in lowered
        or ("year end" in lowered)
    ):
        return datetime(now.year, 12, 31, tzinfo=UTC)
    if "this month" in lowered or "end of the month" in lowered:
        last = _last_day_of_month(now.year, now.month)
        return datetime(now.year, now.month, last, tzinfo=UTC)
    if "next month" in lowered:
        year = now.year + (1 if now.month == 12 else 0)
        month = 1 if now.month == 12 else now.month + 1
        return datetime(year, month, 1, tzinfo=UTC)
    if "next week" in lowered:
        return now + timedelta(weeks=1)
    if "tomorrow" in lowered:
        return now + timedelta(days=1)
    m = _IN_N_UNITS_RE.search(lowered)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("day"):
            return now + timedelta(days=n)
        if unit.startswith("week"):
            return now + timedelta(weeks=n)
        # months: approximate as 30-day steps (deterministic, no calendar math).
        return now + timedelta(days=30 * n)
    return None


def _parse_target_date(message: str, now: datetime) -> datetime | None:
    """Best-effort extraction of a target date from free text (or ``None``)."""
    lowered = message.lower()
    relative = _parse_relative_date(lowered, now)
    if relative is not None:
        return relative
    m = _MONTH_DAY_RE.search(message)
    if m:
        return _build_month_date(
            _MONTHS[m.group(1).lower()], int(m.group(2)), m.group(3), now
        )
    m = _DAY_MONTH_RE.search(message)
    if m:
        return _build_month_date(
            _MONTHS[m.group(2).lower()], int(m.group(1)), m.group(3), now
        )
    m = _MONTH_ONLY_RE.search(message)
    if m:
        # Month with no day → the first of that month.
        return _build_month_date(_MONTHS[m.group(1).lower()], 1, None, now)
    return None


def _infer_priority(
    lowered: str, target_date: datetime | None, now: datetime
) -> GoalPriority:
    """Heuristic priority from urgency markers + target-date proximity."""
    if any(marker in lowered for marker in _LOW_PRIORITY_MARKERS):
        return GoalPriority.LOW
    if any(marker in lowered for marker in _HIGH_PRIORITY_MARKERS):
        return GoalPriority.HIGH
    if target_date is not None:
        days_out = (target_date.date() - now.date()).days
        if 0 <= days_out <= HIGH_PRIORITY_WINDOW_DAYS:
            return GoalPriority.HIGH
    return GoalPriority.MEDIUM


def _clean_title(objective: str) -> str | None:
    """Turn the matched objective into a clean goal title (or reject it).

    Strips a trailing temporal clause, trims punctuation, normalizes spacing,
    and capitalizes the first letter. Rejects (``None``) objectives that read as
    transient questions or are too short to be a real goal.
    """
    title = _TRAILING_DATE_CLAUSE_RE.sub("", objective).strip()
    title = title.strip(" .,!?;:").strip()
    title = re.sub(r"\s+", " ", title)
    if not title:
        return None
    first = title.split(" ", 1)[0].lower()
    # Transient ("know the weather", "ask you something") or too-thin objectives
    # are noise; a single strong verb ("relocate", "graduate") is still a goal.
    if first in _WEAK_OBJECTIVE_VERBS or len(title) < 3:
        return None
    # Capitalize only a lowercase leading letter (preserve acronyms like "AI").
    if title[0].islower():
        title = title[0].upper() + title[1:]
    return title[:GOAL_TITLE_MAX_LENGTH]


def _detect(message: str, now: datetime) -> GoalCandidate | None:
    """Pure detection core (no tracing). See :func:`detect_goal`."""
    stripped = message.strip()
    if not stripped:
        return None
    match = _TRIGGER_RE.search(stripped)
    if match is None:
        return None
    title = _clean_title(match.group(1))
    if title is None:
        return None
    lowered = stripped.lower()
    target_date = _parse_target_date(stripped, now)
    priority = _infer_priority(lowered, target_date, now)
    return GoalCandidate(
        title=title,
        # Keep the user's own words as the description for full context.
        description=stripped,
        priority=priority,
        target_date=target_date,
    )


def detect_goal(message: str, *, now: datetime | None = None) -> GoalCandidate | None:
    """Detect a goal candidate in a user message, or ``None``.

    Deterministic and LLM-free. ``now`` is injectable for testing; it defaults
    to the current UTC time and anchors relative/year-inferred dates. A
    best-effort Langfuse ``goal.extract`` span records whether a goal was
    detected and the resolved title/priority/target date.
    """
    resolved_now = now or datetime.now(UTC)
    with langfuse_obs.observe_operation("goal.extract") as span:
        candidate = _detect(message, resolved_now)
        span.update(
            metadata={
                "detected": candidate is not None,
                "title": candidate.title if candidate else None,
                "priority": candidate.priority.value if candidate else None,
                "target_date": (
                    candidate.target_date.isoformat()
                    if candidate and candidate.target_date
                    else None
                ),
            }
        )
    return candidate
