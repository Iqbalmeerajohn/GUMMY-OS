"""Compose tests (Phase 3, M9): deterministic merge + Personality hook."""

from __future__ import annotations

import pytest

from app.models.enums import PlanShape
from app.schemas.agents import AgentResult
from app.services.agents import compose


def _result(reply: str) -> AgentResult:
    return AgentResult(output={"reply": reply})


def test_single_and_pipeline_use_terminal_reply() -> None:
    results = [("recall", _result("digest")), ("general", _result("final"))]
    assert compose.compose_reply(PlanShape.SINGLE, results) == "final"
    assert compose.compose_reply(PlanShape.PIPELINE, results) == "final"


def test_parallel_single_contribution_unlabeled() -> None:
    results = [("general", _result("only me")), ("recall", _result(""))]
    assert compose.compose_reply(PlanShape.PARALLEL, results) == "only me"


def test_parallel_merge_is_deterministic_and_uses_human_headings() -> None:
    """Agent keys are machinery. "[career]" above a paragraph tells the user
    nothing about their jobs and everything about our package layout."""
    results = [
        ("research", _result("facts here")),
        ("career", _result("answer here")),
    ]

    merged = compose.compose_reply(PlanShape.PARALLEL, results)

    assert merged == "Research\nfacts here\n\nOpportunities\nanswer here"
    assert "[research]" not in merged and "[career]" not in merged
    # Same inputs, same output (deterministic).
    assert compose.compose_reply(PlanShape.PARALLEL, results) == merged


def test_a_failed_branch_is_named_rather_than_dropped() -> None:
    """Silence is the dangerous option: dropping a failed branch reads as a
    complete answer to a half-answered question."""
    results = [("career", _result("three roles found"))]
    failures = [("research", "provider timeout")]

    merged = compose.compose_reply(PlanShape.PARALLEL, results, failures)

    assert "three roles found" in merged
    assert "couldn't complete the research" in merged
    # The raw error is not user-facing — it is already on the step record.
    assert "provider timeout" not in merged


def test_a_single_surviving_branch_needs_no_heading() -> None:
    results = [("career", _result("three roles found"))]

    merged = compose.compose_reply(PlanShape.PARALLEL, results)

    assert merged == "three roles found"


def test_two_failed_branches_are_both_named() -> None:
    results = [("career", _result("roles"))]
    failures = [("research", "boom"), ("learning", "boom")]

    merged = compose.compose_reply(PlanShape.PARALLEL, results, failures)

    assert "the research" in merged and "the learning plan" in merged


def test_parallel_with_no_contributions_says_something() -> None:
    """An empty string reaching the user is indistinguishable from the app
    being broken, so the last step substitutes an honest message."""
    reply = compose.compose_reply(PlanShape.PARALLEL, [])

    assert reply == compose.EMPTY_REPLY_FALLBACK


def test_personality_hook_applied_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(compose, "shape_voice", lambda reply: f"~{reply}~")
    results = [("general", _result("plain"))]
    assert compose.compose_reply(PlanShape.SINGLE, results) == "~plain~"


def test_personality_hook_is_identity_in_phase3() -> None:
    # The parity gates depend on this staying identity until Phase 8.
    assert compose.shape_voice("unchanged") == "unchanged"
