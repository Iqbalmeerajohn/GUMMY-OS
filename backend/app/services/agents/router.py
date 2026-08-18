"""Agent Router — decide who runs and in what shape (Phase 3, M5 → M8).

Layered, rules-first strategy:
  (a) a manual override (``forced_agent_key``) — bypass routing entirely;
  (b) the conversation's ``agent_context`` hint;
  (c) **weighted keyword scoring** across the M8 specialists (deterministic,
      free, explainable) — the highest scorer above a threshold wins (M8);
  (d) an optional LLM fallback on the cheap model tier for ambiguous intent;
  (e) a safe default to the single General agent on low confidence
      (graceful degradation — no request fails because of routing).

Routing is deterministic by default: the keyword scorer (``score_agents``) is
pure and free, so the same intent always routes the same way and the
``/agents/diagnostics`` endpoint can explain it without side effects. The LLM
fallback is opt-in (cost) and only fires when scoring is inconclusive.

The decision is recorded on the run (``route_plan``) for tracing and evals.
"""

from __future__ import annotations

import logging
import re

from app.core.constants import (
    AGENT_ROUTER_KEYWORD_WEIGHT,
    AGENT_ROUTER_MIN_SCORE,
    AGENT_ROUTER_PHRASE_WEIGHT,
    COMPOUND_MAX_STEPS,
    COMPOUND_MIN_CLAUSE_CHARS,
)
from app.models.enums import AgentContext, PlanShape
from app.schemas.agents import AgentManifest, RouteStep, RoutingDecision
from app.services.agents.manifests import (
    GENERAL_AGENT_KEY,
    RECALL_AGENT_KEY,
    SPECIALIST_AGENT_KEYS,
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


# Connectives that separate one task from the next. This is the whole basis of
# compound detection, and the reason it stays conservative: counting keywords
# cannot distinguish "find AI/ML fresher jobs and internships" (four career
# keywords, one task) from "find jobs and then build a learning plan" (two
# tasks). Grammar can. A request with no connective can never fan out.
#
# Ordered longest-first so "and then" is consumed before "and".
_CONNECTIVES: tuple[str, ...] = (
    " and then ",
    " then also ",
    " and after that ",
    " after that ",
    ", and then ",
    ", then ",
    " then ",
    ", and ",
    " and also ",
    " and ",
    ";",
    # A bare comma is included, but it is only safe because of the
    # "two distinct specialists" guard below. "Find jobs, research the
    # companies, and tell me how to prepare" needs it; "jobs in Bangalore,
    # Chennai, or Pune" splits too but yields one specialist, so it collapses
    # straight back to a single step.
    ",",
)

_CONNECTIVE_RE = re.compile("|".join(re.escape(c) for c in _CONNECTIVES), re.IGNORECASE)


def split_clauses(intent: str) -> list[str]:
    """Split a request into the tasks it actually contains.

    Splitting on connectives rather than on punctuation alone: a comma inside
    one task ("jobs in Bangalore, Chennai, or Pune") must not become three
    clauses, whereas "find jobs, and then teach me" must become two.
    """
    parts = [p.strip(" ,.;") for p in _CONNECTIVE_RE.split(intent)]
    return [p for p in parts if len(p) >= COMPOUND_MIN_CLAUSE_CHARS]


def _best_specialist(
    intent: str, registry: AgentRegistry
) -> tuple[str | None, int, list[str]]:
    """The highest-scoring specialist for one clause, or None."""
    lowered = intent.lower()
    registered = registry.keys()
    best_key: str | None = None
    best_score = 0
    best_priority = -1
    best_matched: list[str] = []
    for key in SPECIALIST_AGENT_KEYS:
        if key not in registered:
            continue
        manifest = registry.get(key)
        score, matched = _score_specialist(manifest, lowered)
        if score < AGENT_ROUTER_MIN_SCORE:
            continue
        if (score, manifest.priority) > (best_score, best_priority):
            best_key, best_score, best_priority, best_matched = (
                key,
                score,
                manifest.priority,
                matched,
            )
    return best_key, best_score, best_matched


def plan_compound(intent: str, registry: AgentRegistry) -> RoutingDecision | None:
    """A multi-agent pipeline when the request contains distinct tasks.

    Returns None — meaning "route normally" — unless every condition holds:

    * the request splits on a connective into two or more clauses;
    * at least two clauses resolve to specialists;
    * those specialists are not all the same agent.

    The last condition is what stops "find jobs and internships" fanning out:
    both clauses want Career, so it collapses back to one step. Consecutive
    duplicates are folded rather than deduplicated globally, so a genuine
    A → B → A shape is still expressible.

    Clause order is execution order. "Research X and then teach me" runs
    Research first because that is the order the sentence states, and the
    dependency runs the same way.
    """
    clauses = split_clauses(intent)
    if len(clauses) < 2:
        return None

    resolved: list[tuple[str, str, list[str]]] = []
    for clause in clauses:
        key, _score, matched = _best_specialist(clause, registry)
        if key is None:
            # A clause with no specialist ("tell me how I should prepare") is
            # not dropped silently — it is folded into the previous step's
            # intent, so its wording still reaches an agent.
            if resolved:
                agent_key, prior_intent, prior_matched = resolved[-1]
                resolved[-1] = (agent_key, f"{prior_intent}. {clause}", prior_matched)
            continue
        if resolved and resolved[-1][0] == key:
            # Same agent twice in a row: one task, phrased in two clauses.
            agent_key, prior_intent, prior_matched = resolved[-1]
            resolved[-1] = (
                agent_key,
                f"{prior_intent}. {clause}",
                sorted(set(prior_matched) | set(matched)),
            )
            continue
        resolved.append((key, clause, matched))

    if len({key for key, _, _ in resolved}) < 2:
        return None  # one distinct capability: not compound

    resolved = resolved[:COMPOUND_MAX_STEPS]
    agents = [key for key, _, _ in resolved]
    matched_all = sorted({m for _, _, ms in resolved for m in ms})
    return RoutingDecision(
        plan_shape=PlanShape.PIPELINE,
        steps=[
            RouteStep(agent_key=key, intent=clause_intent)
            for key, clause_intent, _ in resolved
        ],
        rationale=("compound request: " + " then ".join(agents)),
        confidence=0.9,
        matched_keywords=matched_all,
    )


def _keyword_matches(keyword: str, lowered: str) -> bool:
    """True if ``keyword`` occurs in ``lowered``.

    Multi-word phrases match as substrings; single tokens match on word
    boundaries so ``plan`` does not fire on "ex**plan**ation" and ``job`` does
    not fire on "**job**less" — only on whole words (plurals are listed
    explicitly in the manifests).
    """
    kw = keyword.strip().lower()
    if not kw:
        return False
    if " " in kw:
        return kw in lowered
    return re.search(rf"\b{re.escape(kw)}\b", lowered) is not None


def _score_specialist(manifest: AgentManifest, lowered: str) -> tuple[int, list[str]]:
    """Weighted keyword score for one specialist + the keywords that matched."""
    score = 0
    matched: list[str] = []
    for keyword in manifest.keywords:
        if _keyword_matches(keyword, lowered):
            is_phrase = " " in keyword.strip()
            score += (
                AGENT_ROUTER_PHRASE_WEIGHT if is_phrase else AGENT_ROUTER_KEYWORD_WEIGHT
            )
            matched.append(keyword.strip())
    return score, matched


def _confidence_for(score: int) -> float:
    """Map a weighted keyword score to a bounded routing confidence."""
    return min(0.95, 0.6 + 0.12 * score)


def score_agents(intent: str, registry: AgentRegistry) -> RoutingDecision:
    """Deterministically score the specialists and return the routing decision.

    Pure and free (no LLM, no I/O): the highest-scoring specialist above
    ``AGENT_ROUTER_MIN_SCORE`` wins, ties broken by manifest ``priority`` then
    registry order. No specialist clears the bar → the General agent (a safe
    catch-all). Shared by ``route`` and the diagnostics endpoint so both explain
    routing identically.
    """
    lowered = intent.lower()
    registered = registry.keys()
    best_key: str | None = None
    best_score = 0
    best_priority = -1
    best_matched: list[str] = []
    for key in SPECIALIST_AGENT_KEYS:
        if key not in registered:
            continue
        manifest = registry.get(key)
        score, matched = _score_specialist(manifest, lowered)
        if score < AGENT_ROUTER_MIN_SCORE:
            continue
        priority = manifest.priority
        if (score, priority) > (best_score, best_priority):
            best_key, best_score, best_priority, best_matched = (
                key,
                score,
                priority,
                matched,
            )

    if best_key is None:
        return _single("default: no specialist keyword match", confidence=0.3)
    return RoutingDecision(
        plan_shape=PlanShape.SINGLE,
        steps=[RouteStep(agent_key=best_key)],
        rationale=f"matched {', '.join(best_matched)}",
        confidence=_confidence_for(best_score),
        matched_keywords=best_matched,
    )


async def route(
    *,
    intent: str,
    registry: AgentRegistry,
    agent_context: AgentContext | None = None,
    forced_agent_key: str | None = None,
    llm: LLMProvider | None = None,
    fast_model: str | None = None,
) -> RoutingDecision:
    """Classify an intent into a routing decision.

    Manual override and the keyword scorer run without any LLM call; the LLM
    fallback fires only when scoring is inconclusive and an ``llm`` is supplied.
    """
    # (a) Manual override: the user pinned an agent — bypass routing. An unknown
    # key degrades to General (routing must never fail a request).
    if forced_agent_key is not None:
        if forced_agent_key == GENERAL_AGENT_KEY:
            return _single("manual override: general", confidence=1.0)
        registered = registry.keys()
        if forced_agent_key in registered:
            return RoutingDecision(
                plan_shape=PlanShape.SINGLE,
                steps=[RouteStep(agent_key=forced_agent_key)],
                rationale="manual override",
                confidence=1.0,
            )
        logger.warning(
            "unknown forced_agent_key %r; degrading to general", forced_agent_key
        )
        return _single(
            f"manual override: unknown agent {forced_agent_key!r} -> general",
            confidence=1.0,
        )

    # (b) The thread's hub hint: research threads lead with memory recall.
    if agent_context == AgentContext.RESEARCH:
        return _recall_pipeline("agent_context hint: research thread", confidence=0.95)

    # (c) Compound request: distinct tasks joined by a connective become a
    # pipeline. Checked BEFORE single scoring, because single scoring collapses
    # the whole request to its highest-scoring specialist and would silently
    # discard the second task.
    compound = plan_compound(intent, registry)
    if compound is not None:
        return compound

    # (d) Deterministic weighted keyword scoring across the specialists.
    decision = score_agents(intent, registry)
    if decision.steps[0].agent_key != GENERAL_AGENT_KEY:
        return decision

    # (e) LLM fallback on the cheap tier (budget-capped, parse-safe).
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

    # (f) Low confidence → the safe single-agent default.
    return _single("default: low confidence", confidence=0.3)
