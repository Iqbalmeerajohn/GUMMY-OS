"""Router quality eval (Phase 3, M5 → M8).

A labeled intent→agent fixture scored for routing accuracy across the M8
specialist workforce. The rules path is deterministic, so the score is stable;
the floor is deliberately generous so the router can evolve without flaking CI
(this is an eval, not a behavioral contract — see PHASE3_PLAN.md §16).
"""

from __future__ import annotations

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

# (intent, expected agent) — the M8 router routes user-facing intents to the
# five specialists, falling back to General when nothing matches.
_LABELED_INTENTS: list[tuple[str, str]] = [
    # Memory
    ("what do you remember about me?", MEMORY_AGENT_KEY),
    ("recall my fitness goals", MEMORY_AGENT_KEY),
    ("what do you know about my preferences?", MEMORY_AGENT_KEY),
    ("search your memory for my last project", MEMORY_AGENT_KEY),
    # Career
    ("review my resume and apply to jobs", CAREER_AGENT_KEY),
    ("how do I prepare for an interview?", CAREER_AGENT_KEY),
    # Learning
    ("teach me how transformers work", LEARNING_AGENT_KEY),
    ("explain backpropagation to me", LEARNING_AGENT_KEY),
    # Planner
    ("create a 30-day roadmap with milestones", PLANNER_AGENT_KEY),
    ("help me plan my week", PLANNER_AGENT_KEY),
    # Research
    ("compare Rust vs Go", RESEARCH_AGENT_KEY),
    ("research the AI job market", RESEARCH_AGENT_KEY),
    # General fallback
    ("write me a haiku about autumn", GENERAL_AGENT_KEY),
    ("draft an email to my landlord", GENERAL_AGENT_KEY),
    ("what's a good dinner recipe tonight?", GENERAL_AGENT_KEY),
    ("translate good morning into German", GENERAL_AGENT_KEY),
]

_ACCURACY_FLOOR = 0.8


async def test_router_eval_accuracy() -> None:
    registry = get_registry()
    hits = 0
    misses: list[tuple[str, str, str]] = []
    for intent, expected in _LABELED_INTENTS:
        decision = await router.route(intent=intent, registry=registry)
        actual = decision.steps[-1].agent_key
        if actual == expected:
            hits += 1
        else:
            misses.append((intent, expected, actual))
    accuracy = hits / len(_LABELED_INTENTS)
    print(
        f"\nrouter eval: {hits}/{len(_LABELED_INTENTS)} "
        f"(accuracy={accuracy:.2f}); misses={misses}"
    )
    assert accuracy >= _ACCURACY_FLOOR, misses
