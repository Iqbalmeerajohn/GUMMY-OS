"""Router quality eval (Phase 3, M5).

A labeled intent→agent fixture scored for routing accuracy. The rules path is
deterministic, so the score is stable; the floor is deliberately generous so
the router can evolve without flaking CI (this is an eval, not a behavioral
contract — see PHASE3_PLAN.md §16).
"""

from __future__ import annotations

from app.services.agents import router
from app.services.agents.manifests import (
    GENERAL_AGENT_KEY,
    RECALL_AGENT_KEY,
)
from app.services.agents.registry import get_registry

# (intent, expected first agent)
_LABELED_INTENTS: list[tuple[str, str]] = [
    ("what do you remember about me?", RECALL_AGENT_KEY),
    ("recall my fitness goals", RECALL_AGENT_KEY),
    ("do you have any memories of my job search?", RECALL_AGENT_KEY),
    ("what do you know about my study plan?", RECALL_AGENT_KEY),
    ("search your memory for my last project", RECALL_AGENT_KEY),
    ("write me a haiku about autumn", GENERAL_AGENT_KEY),
    ("explain how transformers work", GENERAL_AGENT_KEY),
    ("draft an email to my landlord", GENERAL_AGENT_KEY),
    ("what's a good dinner recipe tonight?", GENERAL_AGENT_KEY),
    ("summarize the pros and cons of Rust vs Go", GENERAL_AGENT_KEY),
    ("help me plan a trip to Japan", GENERAL_AGENT_KEY),
    ("translate 'good morning' into German", GENERAL_AGENT_KEY),
]

_ACCURACY_FLOOR = 0.8


async def test_router_eval_accuracy() -> None:
    registry = get_registry()
    hits = 0
    misses: list[tuple[str, str, str]] = []
    for intent, expected in _LABELED_INTENTS:
        decision = await router.route(intent=intent, registry=registry)
        actual = decision.steps[0].agent_key
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
