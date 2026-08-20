"""Telling SINGLE, PIPELINE and PARALLEL apart.

``_run_parallel`` and ``PlanShape.PARALLEL`` have existed since M9. Nothing
ever produced a PARALLEL decision: ``plan_compound`` returned PIPELINE
unconditionally, so the fan-out path was dead code with tests. What was
missing was the *decision*, and that is what these tests are about.

The asymmetry that drives every choice here: running independent work
sequentially is merely slower, while running dependent work concurrently means
the second agent answers without the information it was supposed to receive.
One is a delay, the other is a wrong answer. So independence has to be
demonstrated — by a neutral connective and no back-reference — and everything
else stays PIPELINE.
"""

from __future__ import annotations

import pytest

from app.models.enums import PlanShape
from app.schemas.agents import AgentResult, CostInfo
from app.services.agents import compose, synthesis
from app.services.agents.registry import get_registry
from app.services.agents.router import plan_compound, route

_REGISTRY = get_registry()


def _shape(intent: str) -> PlanShape | None:
    decision = plan_compound(intent, _REGISTRY)
    return decision.plan_shape if decision else None


def _agents(intent: str) -> list[str]:
    decision = plan_compound(intent, _REGISTRY)
    return [step.agent_key for step in decision.steps] if decision else []


# ── 1–3. SINGLE stays SINGLE ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "intent",
    [
        "Find AI/ML fresher opportunities for me",
        "Research OpenAI, Anthropic and Google AI",
        "Teach me about transformers",
        "Remind me to submit the application tomorrow",
    ],
)
def test_a_single_capability_request_does_not_fan_out(intent: str) -> None:
    assert _shape(intent) is None, "should route normally, not compound"


@pytest.mark.parametrize(
    "intent",
    [
        "Find AI/ML jobs and internships",
        "Find jobs, internships and scholarships",
        "Research OpenAI, Anthropic, and Google DeepMind",
    ],
)
def test_listing_several_things_for_one_specialist_stays_single(intent: str) -> None:
    """The failure this guards: counting keywords cannot tell "jobs and
    internships" (one task) from "jobs and then a study plan" (two)."""
    assert _shape(intent) is None


# ── 4–5. PIPELINE stays PIPELINE ────────────────────────────────────────────


def test_career_then_learning_is_a_pipeline() -> None:
    intent = (
        "Find AI/ML fresher jobs and then create a learning plan for my "
        "biggest skill gap"
    )

    assert _shape(intent) is PlanShape.PIPELINE
    assert _agents(intent) == ["career", "learning"]


def test_research_then_learning_is_a_pipeline() -> None:
    intent = "Research LangGraph and then teach me how to use it"

    assert _shape(intent) is PlanShape.PIPELINE
    assert _agents(intent) == ["research", "learning"]


@pytest.mark.parametrize(
    "intent",
    [
        "Find AI jobs and create a learning plan for my biggest skill gap",
        "Research AI agent companies and apply to them",
        "Research LangGraph and teach me based on that",
        "Find jobs and using the results build a study plan",
        "Find suitable AI jobs, research the companies, and tell me how to prepare",
        "Research the market and remind me about the best one",
    ],
)
def test_a_back_reference_forces_a_pipeline_even_without_then(intent: str) -> None:
    """ "...research THE COMPANIES" points at what the previous clause found.
    Without this, the second agent runs concurrently and answers about
    companies nobody has looked up yet."""
    assert _shape(intent) is PlanShape.PIPELINE


# ── 6. PARALLEL ─────────────────────────────────────────────────────────────


def test_two_independent_tasks_become_parallel() -> None:
    intent = "Find AI/ML fresher jobs for me and research the latest AI agent companies"

    assert _shape(intent) is PlanShape.PARALLEL
    assert _agents(intent) == ["career", "research"]


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        ("Research quantum computing and find me internships", ["research", "career"]),
        ("Teach me Python and remind me to practice daily", ["learning", "automation"]),
    ],
)
def test_other_independent_pairs_also_fan_out(intent: str, expected: list[str]) -> None:
    assert _shape(intent) is PlanShape.PARALLEL
    assert _agents(intent) == expected


def test_the_parallel_rationale_names_the_agents() -> None:
    decision = plan_compound(
        "Find AI/ML jobs and research AI agent companies", _REGISTRY
    )

    assert decision is not None
    assert decision.rationale == "independent tasks: career + research"


async def test_route_surfaces_the_parallel_shape_end_to_end() -> None:
    """plan_compound is consulted by route() before single scoring, which
    would otherwise collapse the request to its highest-scoring specialist."""
    decision = await route(
        intent="Find AI/ML fresher jobs for me and research AI agent companies",
        registry=_REGISTRY,
    )

    assert decision.plan_shape is PlanShape.PARALLEL
    assert {step.agent_key for step in decision.steps} == {"career", "research"}


# ── 7. Overlap is covered where the real dispatch happens ───────────────────
#
# ``test_orchestrator_parallel.test_parallel_branches_run_concurrently`` already
# times two slow branches through ``_run_parallel`` itself. Re-timing
# ``asyncio.gather`` here would assert that the standard library works, not
# that this code uses it.


# ── 8–9. Failure handling ───────────────────────────────────────────────────


def _result(reply: str) -> AgentResult:
    return AgentResult(
        agent_key="x",
        output={"reply": reply},
        cost=CostInfo(tokens=0, usd=0.0),
    )


def test_a_partial_failure_keeps_the_verified_half_and_admits_the_rest() -> None:
    results = [("career", _result("Found 3 fresher roles at X, Y, Z."))]
    failures = [("research", "provider unavailable")]

    reply = compose.compose_reply(PlanShape.PARALLEL, results, failures)

    assert "Found 3 fresher roles at X, Y, Z." in reply
    assert "couldn't complete the research" in reply


def test_a_failed_branch_is_never_invented() -> None:
    """The thing that must not happen: filling the gap with plausible prose."""
    results = [("career", _result("Found 3 roles."))]
    failures = [("research", "boom")]

    reply = compose.compose_reply(PlanShape.PARALLEL, results, failures)

    # Nothing about companies appears, because no company was ever found.
    assert "compan" not in reply.lower()


async def test_synthesis_falls_back_to_the_deterministic_merge_on_failure() -> None:
    """Synthesis is an improvement, never a dependency. If it fails the user
    still gets every branch's content, just less gracefully joined."""

    class _Boom:
        async def generate(self, **_: object) -> object:
            raise RuntimeError("no provider")

    results = [("career", _result("roles here")), ("research", _result("facts here"))]

    reply = await synthesis.synthesize_parallel(results, [], llm=_Boom())  # type: ignore[arg-type]

    assert "roles here" in reply and "facts here" in reply


async def test_a_suspiciously_short_synthesis_is_rejected() -> None:
    """A two-word "synthesis" of two full answers has lost the content; the
    deterministic merge is strictly better than that."""

    class _Terse:
        async def generate(self, **_: object) -> object:
            class _R:
                text = "Sure."

            return _R()

    results = [("career", _result("roles here")), ("research", _result("facts here"))]

    reply = await synthesis.synthesize_parallel(results, [], llm=_Terse())  # type: ignore[arg-type]

    assert "roles here" in reply and "facts here" in reply


def test_the_synthesis_prompt_forbids_inventing_and_hiding() -> None:
    """The two properties that matter more than fluency."""
    system = synthesis._SYSTEM.lower()

    assert "use only what appears" in system
    assert "do not add facts" in system
    assert "could not be completed, say so" in system
    assert "do not mention agents" in system


def test_a_failed_branch_is_named_in_the_synthesis_prompt() -> None:
    body = synthesis._prompt_body(
        [("career", _result("roles here"))], [("research", "boom")]
    )

    assert "roles here" in body
    assert "could not be completed" in body
    # The raw error is not handed to the model either.
    assert "boom" not in body


# ── 13. An unavailable tool is not fabricated around ────────────────────────


def test_web_search_is_not_advertised_when_it_is_unconfigured() -> None:
    """A parallel Research branch with no search backend must degrade
    honestly. The capability block is the single place that claim is made."""
    from app.core.config import get_settings
    from app.services.agents.prompts import identity

    assert not get_settings().web_search_enabled
    block = identity.capability_block()

    assert "search the live web" not in block
    assert "live web search is not connected" in block


def test_research_may_not_name_specifics_without_a_search_backend() -> None:
    """Found live, in a parallel run with no search configured: asked for "the
    latest AI agent companies" the Research branch answered "companies like
    Anthropic, Anthropic, and Google's Anthropic" — one real name, duplicated,
    plus one invented outright.

    Synthesis relayed it faithfully, which is correct behaviour on its part;
    the fabrication was already in the branch. The prompt previously invited
    it by saying to "reason from your training" when no results were
    available.
    """
    from app.services.agents.prompts import research_agent_prompt

    persona = research_agent_prompt.build_persona("anything", "")

    assert "If there is NO Search section, you cannot look anything up" in persona
    assert "do NOT name specific companies" in persona
    assert "never present anything as 'the latest'" in persona
    # The withdrawn licence must not creep back.
    assert "reason from the knowledge and your training" not in persona
