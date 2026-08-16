"""Calendar connector: parsing, ingestion, and the import endpoint."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.connectors import google_calendar
from app.services.memory import timeline

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def _ics(*events: str) -> str:
    body = "\n".join(events)
    return f"BEGIN:VCALENDAR\nVERSION:2.0\n{body}\nEND:VCALENDAR"


def _event(summary: str, stamp: str) -> str:
    return f"BEGIN:VEVENT\nDTSTART:{stamp}\nSUMMARY:{summary}\nEND:VEVENT"


def test_parses_a_past_event() -> None:
    signals = google_calendar.parse_ics(
        _ics(_event("Qualcomm interview", "20260810T090000Z")), now=NOW
    )
    assert [s.content for s in signals] == ["Qualcomm interview"]
    assert signals[0].occurred_at == datetime(2026, 8, 10, 9, 0, tzinfo=UTC)


def test_future_events_are_intentions_not_memories() -> None:
    signals = google_calendar.parse_ics(
        _ics(_event("Dentist", "20261101T090000Z")), now=NOW
    )
    assert signals == []


def test_events_older_than_a_year_are_dropped() -> None:
    signals = google_calendar.parse_ics(
        _ics(_event("Old standup", "20240101T090000Z")), now=NOW
    )
    assert signals == []


def test_calendar_noise_is_skipped() -> None:
    signals = google_calendar.parse_ics(
        _ics(
            _event("Busy", "20260810T090000Z"),
            _event("Lunch", "20260810T120000Z"),
            _event("Ship M9", "20260810T150000Z"),
        ),
        now=NOW,
    )
    assert [s.content for s in signals] == ["Ship M9"]


def test_folded_lines_are_rejoined() -> None:
    """ICS wraps long lines; a naive parser truncates every long summary."""
    folded = (
        "BEGIN:VEVENT\nDTSTART:20260810T090000Z\n"
        "SUMMARY:Architecture review for the\n  memory engine\nEND:VEVENT"
    )
    signals = google_calendar.parse_ics(_ics(folded), now=NOW)
    assert signals[0].content == "Architecture review for the memory engine"


def test_all_day_events_parse() -> None:
    signals = google_calendar.parse_ics(
        _ics("BEGIN:VEVENT\nDTSTART;VALUE=DATE:20260810\nSUMMARY:Offsite\nEND:VEVENT"),
        now=NOW,
    )
    assert [s.content for s in signals] == ["Offsite"]


@pytest.mark.asyncio
async def test_import_lands_on_the_timeline(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Imported events are what makes 'what did I do last week' real."""
    now = datetime.now(UTC)
    stamp = (now - timedelta(days=2)).strftime("%Y%m%dT%H%M%SZ")
    created = await google_calendar.import_from_text(
        db_session, user_id=seed_user, text=_ics(_event("Shipped the parser", stamp))
    )
    assert len(created) == 1

    window = timeline.detect_window("what did I do last week?", now=now)
    assert window is not None
    found = await timeline.events(db_session, user_id=seed_user, window=window)
    assert [m.content for m in found] == ["Shipped the parser"]


@pytest.mark.asyncio
async def test_reimport_does_not_duplicate(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Pointing GUMMY at the same calendar weekly must not pile up copies."""
    stamp = (datetime.now(UTC) - timedelta(days=3)).strftime("%Y%m%dT%H%M%SZ")
    document = _ics(_event("Design review", stamp))

    first = await google_calendar.import_from_text(
        db_session, user_id=seed_user, text=document
    )
    second = await google_calendar.import_from_text(
        db_session, user_id=seed_user, text=document
    )
    assert {m.id for m in first} == {m.id for m in second}


@pytest.mark.asyncio
async def test_import_endpoint_reports_what_it_stored(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    stamp = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y%m%dT%H%M%SZ")
    response = await api_client.post(
        f"/api/v1/connectors/calendar?user_id={seed_user}",
        json={"ics_text": _ics(_event("Retro", stamp))},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["imported"] == 1
    assert body["preview"] == ["Retro"]


@pytest.mark.asyncio
async def test_non_https_url_is_refused(
    api_client: AsyncClient, seed_user: uuid.UUID
) -> None:
    response = await api_client.post(
        f"/api/v1/connectors/calendar?user_id={seed_user}",
        json={"ics_url": "http://example.com/basic.ics"},
    )
    assert response.status_code == 400
