"""Agent Router — decide who runs and in what shape (Phase 3, M5).

Layered, rules-first strategy (PHASE3_PLAN.md §6):
  (a) the conversation's ``agent_context`` hint,
  (b) keyword rules from manifests (deterministic, free),
  (c) an LLM fallback on the cheap model tier for ambiguous intent,
  (d) a safe default to the single general agent on low confidence.

The decision is recorded on the run (``route_plan``) for tracing and evals.
"""

from __future__ import annotations

import logging

from app.models.enums import AgentContext, PlanShape
from app.schemas.agents import RouteStep, RoutingDecision
from app.services.agents.manifests import (
    GENERAL_AGENT_KEY,
    RECALL_AGENT_KEY,
)
from app.services.agents.registry import AgentRegistry
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_LLM_ROUTER_SYSTEM = (
    "You are a routing classifier. Reply with exactly one word: the key of "
    "the agent best suited to the user's message. Known agents: 'general' "
    "(answer anything conversationally) and 'recall' (the user is asking "
    "what is already known/remembered about them). Reply 'general' if unsure."
)
_LLM_ROUTER_MAX_TOKENS = 8


def _single(rationale: str, confidence: float) -> RoutingDecision:
    return RoutingDecision(
        plan_shape=PlanShape.SINGLE,
        steps=[RouteStep(agent_key=GENERAL_AGENT_KEY)],
        rationale=rationale,
        confidence=confidence,
    )


def _recall_pipeline(rationale: str, confidence: float) -> RoutingDecision:
    return RoutingDecision(
        plan_shape=PlanShape.PIPELINE,
        steps=[
            RouteStep(agent_key=RECALL_AGENT_KEY),
            RouteStep(agent_key=GENERAL_AGENT_KEY),
        ],
        rationale=rationale,
        confidence=confidence,
    )


async def route(
    *,
    intent: str,
    registry: AgentRegistry,
    agent_context: AgentContext | None = None,
    llm: LLMProvider | None = None,
    fast_model: str | None = None,
) -> RoutingDecision:
    """Classify an intent into a routing decision. Rules run without any
    LLM call; the LLM fallback fires only when the rules are inconclusive
    and an ``llm`` is supplied."""
    # (a) The thread's hub hint: research threads lead with memory recall.
    if agent_context == AgentContext.RESEARCH:
        return _recall_pipeline(
            "agent_context hint: research thread", confidence=0.95
        )

    # (b) Keyword rules from manifests (specialists only; general is the
    # fallthrough, not a keyword target).
    lowered = intent.lower()
    registered = registry.keys()
    for key in registered:
        if key == GENERAL_AGENT_KEY:
            continue
        manifest = registry.get(key)
        matched = next(
            (kw for kw in manifest.keywords if kw in lowered), None
        )
        if matched is not None:
            return _recall_pipeline(
                f"keyword match: {matched!r} -> {key}", confidence=0.9
            )

    # (c) LLM fallback on the cheap tier (budget-capped, parse-safe).
    if llm is not None:
        try:
            response = await llm.generate(
                system=_LLM_ROUTER_SYSTEM,
                messages=[{"role": "user", "content": intent[:1000]}],
                model=fast_model,
                max_tokens=_LLM_ROUTER_MAX_TOKENS,
            )
            verdict = response.text.strip().lower()
            if RECALL_AGENT_KEY in verdict:
                return _recall_pipeline("llm fallback", confidence=0.6)
            if GENERAL_AGENT_KEY in verdict:
                return _single("llm fallback", confidence=0.6)
        except Exception:
            logger.exception("llm router fallback failed; using default")

    # (d) Low confidence → the safe single-agent default.
    return _single("default: low confidence", confidence=0.3)
