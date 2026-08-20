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

# Same alternation, but capturing, so the connective that joined two clauses
# survives the split. Which connective was used is the strongest available
# signal for whether the second task depends on the first: "and then" states a
# sequence, a bare "and" states nothing.
_CONNECTIVE_CAPTURE_RE = re.compile(
    "(" + "|".join(re.escape(c) for c in _CONNECTIVES) + ")", re.IGNORECASE
)

# Connectives that assert an order. Anything joined by one of these is treated
# as dependent, because that is what the words mean.
_SEQUENCING_JOINS: frozenset[str] = frozenset(
    {"and then", "then also", "and after that", "after that", "then"}
)

# A later clause that refers back to an earlier result is dependent even when
# the connective is a neutral "and": "research the companies and apply to
# them" cannot run its halves at the same time.
#
# Deliberately generous. Misreading independent work as dependent costs
# latency; misreading dependent work as independent produces a second agent
# answering with information it was supposed to be given. Only one of those is
# a wrong answer, so the bias runs toward PIPELINE.
_DEPENDENCY_MARKERS: tuple[str, ...] = (
    r"\bbased on\b",
    r"\busing (the results|those|that|what)\b",
    r"\bfrom (what|the results|those)\b",
    r"\bonce you\b",
    r"\bafter (you|research|find|check)",
    r"\bwith (those|that|the results)\b",
    r"\bfor (the|my|that) (biggest|main|top|largest|weakest)\b",
    r"\bthe (biggest|main|top|largest|weakest|best|first)\b",
    # A definite article on a result-shaped noun, with nothing between them, is
    # pointing at something the previous clause produced: "find jobs, research
    # THE COMPANIES". Requiring the noun to follow "the" immediately is what
    # keeps it narrow — "research the latest AI agent companies" introduces its
    # own subject and stays independent.
    r"\bthe (compan(y|ies)|role|roles|job|jobs|listing|listings"
    r"|result|results|option|options|gap|gaps|one|ones)\b",
    r"\b(those|them|these)\b",
    r"\beach (one|of them)\b",
    r"\bthat (gap|role|company|topic|one|result)\b",
)
_DEPENDENCY_RE = re.compile("|".join(_DEPENDENCY_MARKERS), re.IGNORECASE)


def _segments(intent: str) -> list[tuple[str, str]]:
    """Split into ``(clause, joining_connective)`` pairs.

    The connective recorded against a clause is the one that came *before* it,
    so ``segments[i][1]`` describes the relationship between clause ``i-1`` and
    clause ``i``. The first clause has no preceding connective.
    """
    parts = _CONNECTIVE_CAPTURE_RE.split(intent)
    segments: list[tuple[str, str]] = []
    for index in range(0, len(parts), 2):
        clause = parts[index].strip(" ,.;")
        join = parts[index - 1].strip(" ,").lower() if index > 0 else ""
        if len(clause) >= COMPOUND_MIN_CLAUSE_CHARS:
            segments.append((clause, join))
    return segments


def split_clauses(intent: str) -> list[str]:
    """Split a request into the tasks it actually contains.

    Splitting on connectives rather than on punctuation alone: a comma inside
    one task ("jobs in Bangalore, Chennai, or Pune") must not become three
    clauses, whereas "find jobs, and then teach me" must become two.
    """
    return [clause for clause, _join in _segments(intent)]


def _depends_on_earlier(clause: str, join: str) -> bool:
    """Whether this clause needs the previous clause's result to run."""
    return join in _SEQUENCING_JOINS or bool(_DEPENDENCY_RE.search(clause))


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
    """A multi-agent plan when the request contains distinct tasks.

    Returns None — meaning "route normally" — unless every condition holds:

    * the request splits on a connective into two or more clauses;
    * at least two clauses resolve to specialists;
    * those specialists are not all the same agent.

    The last condition is what stops "find jobs and internships" fanning out:
    both clauses want Career, so it collapses back to one step. Consecutive
    duplicates are folded rather than deduplicated globally, so a genuine
    A → B → A shape is still expressible.

    Clause order is execution order either way. What differs is the *shape*:

    * **PIPELINE** when a later task needs an earlier one's result — stated by
      the connective ("and then") or by a back-reference ("...for my biggest
      gap", "...apply to them").
    * **PARALLEL** when the tasks are merely listed together and neither refers
      to the other.

    PIPELINE is the default of the two. Running independent work sequentially
    is slower; running dependent work concurrently means the second agent
    answers without the information it was supposed to receive. Only one of
    those is a wrong answer, so independence has to be shown, not assumed.
    """
    segments = _segments(intent)
    if len(segments) < 2:
        return None

    # (agent_key, intent, matched_keywords, depends_on_previous)
    resolved: list[tuple[str, str, list[str], bool]] = []
    for clause, join in segments:
        key, _score, matched = _best_specialist(clause, registry)
        dependent = _depends_on_earlier(clause, join)
        if key is None:
            # A clause with no specialist ("tell me how I should prepare") is
            # not dropped silently — it is folded into the previous step's
            # intent, so its wording still reaches an agent.
            if resolved:
                agent_key, prior_intent, prior_matched, prior_dep = resolved[-1]
                resolved[-1] = (
                    agent_key,
                    f"{prior_intent}. {clause}",
                    prior_matched,
                    prior_dep,
                )
            continue
        if resolved and resolved[-1][0] == key:
            # Same agent twice in a row: one task, phrased in two clauses.
            agent_key, prior_intent, prior_matched, prior_dep = resolved[-1]
            resolved[-1] = (
                agent_key,
                f"{prior_intent}. {clause}",
                sorted(set(prior_matched) | set(matched)),
                prior_dep,
            )
            continue
        resolved.append((key, clause, matched, dependent))

    if len({key for key, _, _, _ in resolved}) < 2:
        return None  # one distinct capability: not compound

    resolved = resolved[:COMPOUND_MAX_STEPS]
    agents = [key for key, _, _, _ in resolved]
    matched_all = sorted({m for _, _, ms, _ in resolved for m in ms})

    # Only steps after the first can depend on anything.
    dependent = any(dep for _, _, _, dep in resolved[1:])
    if dependent:
        shape = PlanShape.PIPELINE
        rationale = "compound request: " + " then ".join(agents)
    else:
        shape = PlanShape.PARALLEL
        rationale = "independent tasks: " + " + ".join(agents)

    return RoutingDecision(
        plan_shape=shape,
        steps=[
            RouteStep(agent_key=key, intent=clause_intent)
            for key, clause_intent, _, _ in resolved
        ],
        rationale=rationale,
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
