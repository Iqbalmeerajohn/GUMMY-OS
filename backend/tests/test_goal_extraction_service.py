"""Goal extraction tests (M5.5): deterministic detection, date parsing,
priority heuristics, and the negative cases that must NOT become goals."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.enums import GoalPriority
from app.services.goals import goal_extraction_service as extract

# Fixed "now" so year-inferred and relative dates are deterministic.
_NOW = datetime(2026, 6, 23, tzinfo=UTC)


# ── Positive examples ─────────────────────────────────────────────────────────


def test_acceptance_example_ai_engineer_job() -> None:
    candidate = extract.detect_goal(
        "I want to get an AI Engineer job by July 2nd", now=_NOW
    )
    assert candidate is not None
    assert candidate.title == "Get an AI Engineer job"
    assert candidate.priority is GoalPriority.HIGH  # target within 30 days
    assert candidate.target_date is not None
    assert candidate.target_date.date().isoformat() == "2026-07-02"
    # The user's words are retained as the description.
    assert candidate.description == "I want to get an AI Engineer job by July 2nd"


@pytest.mark.parametrize(
    ("message", "title"),
    [
        ("I want to get an AI Engineer job by July 2nd", "Get an AI Engineer job"),
        ("I need to lose 10kg this year", "Lose 10kg"),
        ("My goal is to launch GUMMY SaaS", "Launch GUMMY SaaS"),
        ("I want to finish all backlogs by August", "Finish all backlogs"),
        ("I plan to apply for 100 jobs", "Apply for 100 jobs"),
        ("I aim to read 12 books", "Read 12 books"),
        ("I am trying to run a marathon", "Run a marathon"),
    ],
)
def test_detects_goal_and_strips_trigger_and_date(
    message: str, title: str
) -> None:
    candidate = extract.detect_goal(message, now=_NOW)
    assert candidate is not None
    assert candidate.title == title


def test_my_goal_is_without_to() -> None:
    candidate = extract.detect_goal("My goal is financial freedom", now=_NOW)
    assert candidate is not None
    assert candidate.title == "Financial freedom"


def test_trigger_mid_sentence_after_comma() -> None:
    candidate = extract.detect_goal(
        "Honestly, I want to launch my startup", now=_NOW
    )
    assert candidate is not None
    assert candidate.title == "Launch my startup"


# ── Date parsing ──────────────────────────────────────────────────────────────


def test_month_day_with_explicit_year() -> None:
    candidate = extract.detect_goal(
        "I plan to ship the app by March 5, 2027", now=_NOW
    )
    assert candidate is not None
    assert candidate.target_date is not None
    assert candidate.target_date.date().isoformat() == "2027-03-05"


def test_past_month_day_rolls_to_next_year() -> None:
    # January is already past on 2026-06-23 → inferred as 2027.
    candidate = extract.detect_goal("I want to relocate by January 10", now=_NOW)
    assert candidate is not None
    assert candidate.target_date is not None
    assert candidate.target_date.date().isoformat() == "2027-01-10"


def test_this_year_maps_to_year_end() -> None:
    candidate = extract.detect_goal("I want to save $5000 this year", now=_NOW)
    assert candidate is not None
    assert candidate.target_date is not None
    assert candidate.target_date.date().isoformat() == "2026-12-31"


def test_relative_in_n_weeks() -> None:
    candidate = extract.detect_goal(
        "I plan to launch the beta in 2 weeks", now=_NOW
    )
    assert candidate is not None
    assert candidate.target_date is not None
    assert candidate.target_date.date().isoformat() == "2026-07-07"


def test_goal_without_date_has_no_target() -> None:
    candidate = extract.detect_goal("I want to learn Spanish", now=_NOW)
    assert candidate is not None
    assert candidate.target_date is None


# ── Priority heuristics ───────────────────────────────────────────────────────


def test_urgency_marker_forces_high() -> None:
    candidate = extract.detect_goal(
        "I need to finish the deck asap", now=_NOW
    )
    assert candidate is not None
    assert candidate.priority is GoalPriority.HIGH


def test_someday_marker_forces_low() -> None:
    candidate = extract.detect_goal(
        "I want to visit Japan someday", now=_NOW
    )
    assert candidate is not None
    assert candidate.priority is GoalPriority.LOW


def test_far_off_goal_is_medium() -> None:
    candidate = extract.detect_goal("I want to learn the violin", now=_NOW)
    assert candidate is not None
    assert candidate.priority is GoalPriority.MEDIUM


# ── Negative examples (must NOT become goals) ─────────────────────────────────


@pytest.mark.parametrize(
    "message",
    [
        "What should I do today?",
        "Do you want to help me?",
        "Can you remind me later?",
        "I want pizza",  # "i want" without an infinitive objective
        "I want to know the weather",  # transient question
        "I need to ask you something",  # transient question
        "How do I get a job?",
        "You need to refactor this function",  # not the user's own intent
        "Tell me a joke",
        "",
        "   ",
    ],
)
def test_non_goals_return_none(message: str) -> None:
    assert extract.detect_goal(message, now=_NOW) is None


def test_invalid_calendar_date_yields_no_target_but_still_detects() -> None:
    # Feb 30 is invalid → no target date, but it's still a goal.
    candidate = extract.detect_goal(
        "I want to finish the report by February 30", now=_NOW
    )
    assert candidate is not None
    assert candidate.target_date is None
