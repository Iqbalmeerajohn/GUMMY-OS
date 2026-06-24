"""Agent Router tests (Phase 3, M8): deterministic weighted scoring.

The M8 gates: each specialist wins its own intents, the highest weighted keyword
score wins (ties broken by priority), a no-match degrades to General (graceful
degradation), and a manual override bypasses scoring. ``score_agents`` is pure
and free — the diagnostics endpoint relies on it being side-effect-free.
"""

from __future__ import annotations

import pytest

from app.models.enums import PlanShape
from app.services.agents import router
from app.services.agents.manifests import (
    CAREER_AGENT_KEY,
    GENERAL_AGENT_KEY,
    LEARNING_AGENT_KEY,
    MEMORY_AGENT_KEY,
    PLANNER_AGENT_KEY,
    RESEARCH_AGENT_KEY,
)
from app.services.agents.registry import get_registry


def _selected(intent: str) -> str:
    decision = router.score_agents(intent, get_registry())
    return decision.steps[-1].agent_key


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        ("Based on my resume what jobs should I apply for?", CAREER_AGENT_KEY),
        ("Review my resume", CAREER_AGENT_KEY),
        ("How can I get an AI Engineer role? interview prep", CAREER_AGENT_KEY),
        ("Teach me transformers", LEARNING_AGENT_KEY),
        ("Create a roadmap for deep learning", LEARNING_AGENT_KEY),
        ("Explain how diffusion models work", LEARNING_AGENT_KEY),
        ("Create a 30-day roadmap", PLANNER_AGENT_KEY),
        ("Break my goal into milestones with a timeline", PLANNER_AGENT_KEY),
        ("What do you know about me?", MEMORY_AGENT_KEY),
        ("Summarize my memories", MEMORY_AGENT_KEY),
        ("Compare AI Engineer vs Data Engineer", RESEARCH_AGENT_KEY),
        ("Research the AI job market trends", RESEARCH_AGENT_KEY),
    ],
)
def test_specialist_routing(intent: str, expected: str) -> None:
    assert _selected(intent) == expected


@pytest.mark.parametrize(
    "intent",
    [
        "just chatting about the weather",
        "tell me a joke",
        "hello there",
    ],
)
def test_no_match_degrades_to_general(intent: str) -> None:
    decision = router.score_agents(intent, get_registry())
    assert decision.steps[-1].agent_key == GENERAL_AGENT_KEY
    assert decision.plan_shape == PlanShape.SINGLE
    assert decision.confidence < 0.5


def test_weighted_score_beats_single_keyword() -> None:
    # "research ... compare ... vs" outscores the lone career "job" keyword.
    decision = router.score_agents(
        "research and compare the AI job market vs data roles", get_registry()
    )
    assert decision.steps[-1].agent_key == RESEARCH_AGENT_KEY


def test_rationale_lists_matched_keywords() -> None:
    decision = router.score_agents("Review my resume and jobs", get_registry())
    assert decision.steps[-1].agent_key == CAREER_AGENT_KEY
    assert "resume" in decision.rationale
    assert "jobs" in decision.rationale


def test_word_boundary_avoids_false_match() -> None:
    # "explanation" must NOT trigger Planner via the "plan" keyword.
    decision = router.score_agents(
        "give me an explanation of recursion", get_registry()
    )
    assert decision.steps[-1].agent_key != PLANNER_AGENT_KEY


async def test_manual_override_bypasses_scoring() -> None:
    # A career-shaped message, but Research is pinned → Research wins.
    decision = await router.route(
        intent="review my resume",
        registry=get_registry(),
        forced_agent_key=RESEARCH_AGENT_KEY,
    )
    assert decision.steps[-1].agent_key == RESEARCH_AGENT_KEY
    assert decision.rationale == "manual override"
    assert decision.confidence == 1.0


async def test_unknown_override_degrades_to_general() -> None:
    decision = await router.route(
        intent="anything",
        registry=get_registry(),
        forced_agent_key="does-not-exist",
    )
    assert decision.steps[-1].agent_key == GENERAL_AGENT_KEY


def test_score_agents_is_pure() -> None:
    # Same input → same decision, no state mutation between calls.
    reg = get_registry()
    a = router.score_agents("Review my resume", reg)
    b = router.score_agents("Review my resume", reg)
    assert a.model_dump() == b.model_dump()
