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


def test_parallel_merge_is_deterministic_and_labeled() -> None:
    results = [
        ("recall", _result("facts here")),
        ("general", _result("answer here")),
    ]
    merged = compose.compose_reply(PlanShape.PARALLEL, results)
    assert merged == "[recall]\nfacts here\n\n[general]\nanswer here"
    # Same inputs, same output (deterministic).
    assert compose.compose_reply(PlanShape.PARALLEL, results) == merged


def test_parallel_empty_contributions() -> None:
    assert compose.compose_reply(PlanShape.PARALLEL, []) == ""


def test_personality_hook_applied_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(compose, "shape_voice", lambda reply: f"~{reply}~")
    results = [("general", _result("plain"))]
    assert compose.compose_reply(PlanShape.SINGLE, results) == "~plain~"


def test_personality_hook_is_identity_in_phase3() -> None:
    # The parity gates depend on this staying identity until Phase 8.
    assert compose.shape_voice("unchanged") == "unchanged"
