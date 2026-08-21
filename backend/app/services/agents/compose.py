"""Compose — merge agent outputs into one reply (Phase 3, M9).

Deterministic, LLM-free merging:
- single/pipeline → the terminal agent's reply, unchanged;
- parallel → successful branches merged in dispatch order, each section
  given a human heading when more than one branch contributed.

This is the floor, not the ceiling: a parallel run normally passes through the
LLM synthesis in :mod:`app.services.agents.synthesis` first, and falls back
here when that is unavailable or fails. Keeping the fallback deterministic
means a synthesis outage degrades the *prose*, never the *content*.

``shape_voice`` is the Personality hook (PHASE3_PLAN.md §14.5): applied
**last**, identity until the Personality layer ships — which is what keeps
the M4/M11 parity gates true.
"""

from __future__ import annotations

from app.models.enums import PlanShape
from app.schemas.agents import AgentResult

# Headings a person would recognise. Agent *keys* are internal machinery and
# must not reach the user — "[career]" above a paragraph tells them nothing
# about their jobs and everything about our package layout.
_SECTION_HEADINGS: dict[str, str] = {
    "career": "Opportunities",
    "learning": "Learning",
    "research": "Research",
    "automation": "Reminders",
    "planner": "Plan",
    "memory": "From your memory",
    "recall": "From your memory",
    "general": "Answer",
}

# What each branch was doing, phrased for an apology rather than a heading.
_FAILURE_NOUNS: dict[str, str] = {
    "career": "the opportunities search",
    "learning": "the learning plan",
    "research": "the research",
    "automation": "the reminder",
    "planner": "the plan",
    "memory": "the memory lookup",
    "recall": "the memory lookup",
    "general": "part of this",
}


def heading_for(agent_key: str) -> str:
    """A user-facing section heading for an agent branch."""
    return _SECTION_HEADINGS.get(agent_key, agent_key.replace("_", " ").title())


def failure_noun_for(agent_key: str) -> str:
    """How to name a branch when telling the user it did not complete."""
    return _FAILURE_NOUNS.get(agent_key, f"the {agent_key} step")


def shape_voice(reply: str) -> str:
    """The Personality layer's seam. Identity in Phase 3 — replacing this is
    a Phase 8 (roadmap) change, gated on re-proving reply parity."""
    return reply


def _reply_of(result: AgentResult) -> str:
    return str(result.output.get("reply", "")).strip()


def failure_note(failures: list[tuple[str, str]]) -> str:
    """One plain sentence naming what could not be completed.

    Silence here is the dangerous option: a parallel run that quietly drops a
    failed branch reads as a complete answer to a question that was only half
    answered. The error text itself is deliberately not shown — it is a stack
    trace's worth of detail the user cannot act on, and it is already in the
    step record.
    """
    if not failures:
        return ""
    nouns = [failure_noun_for(agent_key) for agent_key, _error in failures]
    if len(nouns) == 1:
        subject = nouns[0]
    else:
        subject = ", ".join(nouns[:-1]) + f" and {nouns[-1]}"
    return f"I couldn't complete {subject} this time, so that part is missing."


def merge_parallel(
    results: list[tuple[str, AgentResult]],
    failures: list[tuple[str, str]] | None = None,
) -> str:
    """Merge parallel branch outputs deterministically (dispatch order)."""
    contributions = [
        (agent_key, _reply_of(result))
        for agent_key, result in results
        if _reply_of(result)
    ]
    note = failure_note(failures or [])

    if not contributions:
        return note

    if len(contributions) == 1:
        body = contributions[0][1]
    else:
        body = "\n\n".join(
            f"{heading_for(agent_key)}\n{reply}" for agent_key, reply in contributions
        )
    return f"{body}\n\n{note}" if note else body


# Shown when the model produces nothing at all. Observed live: a Research turn
# that ran its search, got five sources, called a tool, and then emitted zero
# characters — the user received an empty message bubble. Rare, but an empty
# answer is indistinguishable from the app being broken, and it is never the
# right thing to show.
EMPTY_REPLY_FALLBACK = (
    "I wasn't able to put an answer together for that one. Could you try "
    "rephrasing it, or narrowing it to the part you most want?"
)


def compose_reply(
    plan_shape: PlanShape,
    results: list[tuple[str, AgentResult]],
    failures: list[tuple[str, str]] | None = None,
) -> str:
    """Produce the final reply for a run; Personality voice applied last."""
    if plan_shape == PlanShape.PARALLEL:
        reply = merge_parallel(results, failures)
    else:
        reply = _reply_of(results[-1][1]) if results else ""
    if not reply.strip():
        reply = EMPTY_REPLY_FALLBACK
    return shape_voice(reply)
