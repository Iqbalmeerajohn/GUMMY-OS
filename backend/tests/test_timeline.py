"""Episodic timeline: anchoring facts in time and reading them back."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory, MemoryStatus
from app.models.memory import Memory
from app.services.memory import timeline

NOW = datetime(2026, 8, 12, 10, 0, tzinfo=UTC)  # a Wednesday


# ── parse_occurred_at ────────────────────────────────────────────────────────


def test_timeless_fact_has_no_anchor() -> None:
    assert timeline.parse_occurred_at("Lives in Vizag", now=NOW) is None


def test_yesterday() -> None:
    parsed = timeline.parse_occurred_at("Shipped M8 yesterday", now=NOW)
    assert parsed == NOW - timedelta(days=1)


def test_n_units_ago() -> None:
    assert timeline.parse_occurred_at(
        "Finished the migration 3 weeks ago", now=NOW
    ) == NOW - timedelta(days=21)


def test_named_weekday_resolves_to_the_most_recent_past_one() -> None:
    # NOW is a Wednesday; "last Monday" is two days back.
    assert timeline.parse_occurred_at(
        "Presented the plan last Monday", now=NOW
    ) == NOW - timedelta(days=2)


def test_weekday_named_today_means_a_week_ago() -> None:
    """The phrasing is retrospective, so 'last Wednesday' is not today."""
    assert timeline.parse_occurred_at(
        "Deployed on Wednesday", now=NOW
    ) == NOW - timedelta(days=7)


def test_future_phrases_are_ignored() -> None:
    """Future intentions are goals, and goals have their own model."""
    assert timeline.parse_occurred_at("Ships next Friday", now=NOW) is None


# ── detect_window ────────────────────────────────────────────────────────────


def test_date_word_alone_is_not_a_retrospective_question() -> None:
    assert timeline.detect_window("remind me to ship this week", now=NOW) is None


def test_retrospective_question_opens_a_window() -> None:
    window = timeline.detect_window("what did I do last week?", now=NOW)
    assert window is not None
    assert window.label == "this week"
    assert window.start == NOW - timedelta(days=7)


def test_question_without_a_time_phrase_has_no_window() -> None:
    assert timeline.detect_window("what did I do about the bug?", now=NOW) is None


# ── read path ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_events_returns_only_anchored_memories_in_window(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    now = datetime.now(UTC)
    db_session.add_all(
        [
            Memory(
                user_id=seed_user,
                category=MemoryCategory.PROJECT,
                content="Shipped the auth rewrite",
                importance_score=0.5,
                confidence_score=0.5,
                status=MemoryStatus.ACTIVE,
                occurred_at=now - timedelta(days=2),
            ),
            Memory(
                user_id=seed_user,
                category=MemoryCategory.PROJECT,
                content="Started GUMMY",
                importance_score=0.5,
                confidence_score=0.5,
                status=MemoryStatus.ACTIVE,
                occurred_at=now - timedelta(days=200),
            ),
            Memory(
                user_id=seed_user,
                category=MemoryCategory.PROFILE,
                content="Lives in Vizag",
                importance_score=0.5,
                confidence_score=0.5,
                status=MemoryStatus.ACTIVE,
            ),
        ]
    )
    await db_session.commit()

    window = timeline.detect_window("what did I do last week?", now=now)
    assert window is not None
    found = await timeline.events(db_session, user_id=seed_user, window=window)

    assert [m.content for m in found] == ["Shipped the auth rewrite"]
    rendered = timeline.render(window, found)
    assert rendered is not None
    assert "auth rewrite" in rendered


@pytest.mark.asyncio
async def test_empty_window_renders_nothing(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """No record is a fact about what was written down, not about the user."""
    window = timeline.detect_window("what did I do last week?", now=datetime.now(UTC))
    assert window is not None
    assert timeline.render(window, []) is None
