"""Google Calendar connector — the user's real week, from their own calendar.

Reads a calendar's **secret iCal address** (Google Calendar → Settings → *Secret
address in iCal format*) rather than the Calendar API. That choice is the whole
point of this connector:

* it needs no OAuth scopes, no token storage, and no Google app review, so it
  works on a machine that is offline from everything except that one URL;
* the same code path ingests a ``.ics`` file exported from Apple Calendar,
  Outlook, or Google Takeout, so one small parser covers every calendar the user
  might have.

Only *past* events are imported. Future entries are intentions, and intentions
are goals — GUMMY already models those, and importing them as memories would
tell the assistant the user did things they have not done.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.enums import MemoryCategory
from app.models.memory import Memory
from app.services.connectors import base
from app.services.connectors.base import Signal

# A calendar feed is text; anything this large is not one, and streaming a
# surprise gigabyte into memory is the failure mode worth precluding.
_MAX_BYTES = 5_000_000
_TIMEOUT_SECONDS = 20.0

# How far back an import reaches. A year of history is plenty to know someone;
# beyond that the events stop describing who they are now.
_MAX_AGE = timedelta(days=365)

# ICS folds long lines by starting continuations with a space or tab.
_UNFOLD = re.compile(r"\r?\n[ \t]")
_EVENT = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.DOTALL)
_SUMMARY = re.compile(r"^SUMMARY(?:;[^:]*)?:(.*)$", re.MULTILINE)
_DTSTART = re.compile(r"^DTSTART(?:;[^:]*)?:([0-9TZ]+)$", re.MULTILINE)

# Recurring noise that says nothing about the person. Cheap to skip here, and
# every one skipped is a prompt slot left for something that matters.
_IGNORED = re.compile(
    r"^(busy|blocked?|hold|ooo|out of office|lunch|focus time|"
    r"tentative|no meetings?)$",
    re.IGNORECASE,
)


def _parse_timestamp(raw: str) -> datetime | None:
    """Parse an ICS DTSTART: ``20260812T093000Z`` or a date-only ``20260812``."""
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def parse_ics(text: str, *, now: datetime | None = None) -> list[Signal]:
    """Extract past, meaningful events from an iCalendar document.

    Pure and offline, so it is equally the parser for a pasted file and for a
    fetched URL — and testable without a network.
    """
    reference = now or datetime.now(UTC)
    oldest = reference - _MAX_AGE
    unfolded = _UNFOLD.sub("", text)

    signals: list[Signal] = []
    for block in _EVENT.findall(unfolded):
        summary_match = _SUMMARY.search(block)
        start_match = _DTSTART.search(block)
        if summary_match is None or start_match is None:
            continue
        summary = summary_match.group(1).strip().replace("\\,", ",")
        occurred_at = _parse_timestamp(start_match.group(1).strip())
        if not summary or occurred_at is None:
            continue
        if occurred_at > reference or occurred_at < oldest:
            continue
        if _IGNORED.match(summary):
            continue
        signals.append(
            Signal(
                content=summary,
                category=MemoryCategory.PROJECT,
                occurred_at=occurred_at,
            )
        )
    return signals


async def _fetch(url: str) -> str:
    """Download a calendar feed, refusing anything that is not plausibly one."""
    if not url.startswith("https://"):
        raise AppError(
            "The calendar URL must be an https address.",
            code="invalid_calendar_url",
            status_code=400,
        )
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AppError(
            "That calendar could not be reached.",
            code="calendar_unreachable",
            status_code=502,
        ) from exc
    if len(response.content) > _MAX_BYTES:
        raise AppError(
            "That calendar feed is too large to import.",
            code="calendar_too_large",
            status_code=413,
        )
    return response.text


async def import_from_url(
    session: AsyncSession, *, user_id: uuid.UUID, url: str
) -> list[Memory]:
    """Fetch a calendar feed and fold its past events into memory."""
    signals = parse_ics(await _fetch(url))
    return await base.ingest(session, user_id=user_id, signals=signals)


async def import_from_text(
    session: AsyncSession, *, user_id: uuid.UUID, text: str
) -> list[Memory]:
    """Fold a pasted or uploaded ``.ics`` document into memory."""
    return await base.ingest(session, user_id=user_id, signals=parse_ics(text))
