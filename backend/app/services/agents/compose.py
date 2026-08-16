"""Compose — merge agent outputs into one reply (Phase 3, M9).

Deterministic, LLM-free merging:
- single/pipeline → the terminal agent's reply, unchanged;
- parallel → successful branches merged in dispatch order, each section
  labeled by its agent when more than one branch contributed.

``shape_voice`` is the Personality hook (PHASE3_PLAN.md §14.5): applied
**last**, identity until the Personality layer ships — which is what keeps
the M4/M11 parity gates true.
"""

from __future__ import annotations

from app.models.enums import PlanShape
from app.schemas.agents import AgentResult


def shape_voice(reply: str) -> str:
    """The Personality layer's seam. Identity in Phase 3 — replacing this is
    a Phase 8 (roadmap) change, gated on re-proving reply parity."""
    return reply


def _reply_of(result: AgentResult) -> str:
    return str(result.output.get("reply", "")).strip()


def merge_parallel(results: list[tuple[str, AgentResult]]) -> str:
    """Merge parallel branch outputs deterministically (dispatch order)."""
    contributions = [
        (agent_key, _reply_of(result))
        for agent_key, result in results
        if _reply_of(result)
    ]
    if not contributions:
        return ""
    if len(contributions) == 1:
        return contributions[0][1]
    return "\n\n".join(f"[{agent_key}]\n{reply}" for agent_key, reply in contributions)


def compose_reply(plan_shape: PlanShape, results: list[tuple[str, AgentResult]]) -> str:
    """Produce the final reply for a run; Personality voice applied last."""
    if plan_shape == PlanShape.PARALLEL:
        reply = merge_parallel(results)
    else:
        reply = _reply_of(results[-1][1]) if results else ""
    return shape_voice(reply)
