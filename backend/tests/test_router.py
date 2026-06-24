"""Router tests (Phase 3, M5): rules-first, LLM-last, safe default."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.models.enums import AgentContext, PlanShape
from app.services.agents import router
from app.services.agents.manifests import (
    CAREER_AGENT_KEY,
    GENERAL_AGENT_KEY,
    MEMORY_AGENT_KEY,
    RECALL_AGENT_KEY,
)
from app.services.agents.registry import get_registry
from app.services.llm.base import LLMResponse


@dataclass
class _SpyLLM:
    """Counts calls; returns a fixed routing verdict."""

    verdict: str = "general"
    calls: int = 0
    last_model: str | None = None
    last_max_tokens: int | None = None

    @property
    def name(self) -> str:
        return "spy"

    async def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls += 1
        self.last_model = model
        self.last_max_tokens = max_tokens
        return LLMResponse(
            text=self.verdict,
            model=model or "spy-model",
            input_tokens=10,
            output_tokens=2,
            stop_reason="end_turn",
        )


async def test_agent_context_hint_routes_without_llm() -> None:
    llm = _SpyLLM()
    decision = await router.route(
        intent="tell me something",
        registry=get_registry(),
        agent_context=AgentContext.RESEARCH,
        llm=llm,
    )
    assert decision.plan_shape == PlanShape.PIPELINE
    assert [s.agent_key for s in decision.steps] == [
        RECALL_AGENT_KEY,
        GENERAL_AGENT_KEY,
    ]
    assert decision.confidence >= 0.9
    assert llm.calls == 0  # deterministic path: no LLM


async def test_keyword_rule_routes_without_llm() -> None:
    # M8: a clear specialist keyword routes to that specialist (SINGLE), free.
    llm = _SpyLLM()
    decision = await router.route(
        intent="What jobs should I apply for?",
        registry=get_registry(),
        llm=llm,
    )
    assert decision.plan_shape == PlanShape.SINGLE
    assert decision.steps[0].agent_key == CAREER_AGENT_KEY
    assert "matched" in decision.rationale
    assert llm.calls == 0  # deterministic path: no LLM


async def test_ambiguous_intent_uses_llm_fallback_on_cheap_tier() -> None:
    llm = _SpyLLM(verdict="recall")
    decision = await router.route(
        intent="hmm, interesting question about my past",
        registry=get_registry(),
        llm=llm,
        fast_model="cheap-model",
    )
    assert llm.calls == 1
    assert llm.last_model == "cheap-model"  # the claude_model_fast seam
    assert llm.last_max_tokens is not None
    assert llm.last_max_tokens <= 16  # budget-capped classifier call
    assert decision.steps[0].agent_key == RECALL_AGENT_KEY
    assert decision.rationale == "llm fallback"


async def test_unparseable_llm_verdict_falls_back_to_general() -> None:
    llm = _SpyLLM(verdict="banana")
    decision = await router.route(
        intent="completely ambiguous", registry=get_registry(), llm=llm
    )
    assert decision.plan_shape == PlanShape.SINGLE
    assert decision.steps[0].agent_key == GENERAL_AGENT_KEY
    assert decision.confidence <= 0.5


async def test_llm_failure_falls_back_to_general() -> None:
    class _Boom:
        @property
        def name(self) -> str:
            return "boom"

        async def generate(self, **kwargs: object) -> LLMResponse:
            raise RuntimeError("router llm down")

    decision = await router.route(
        intent="ambiguous", registry=get_registry(), llm=_Boom()
    )
    assert decision.steps[0].agent_key == GENERAL_AGENT_KEY


async def test_no_llm_default_is_single_general() -> None:
    decision = await router.route(
        intent="just chatting about the weather",
        registry=get_registry(),
        llm=None,
    )
    assert decision.plan_shape == PlanShape.SINGLE
    assert [s.agent_key for s in decision.steps] == [GENERAL_AGENT_KEY]
    assert decision.rationale == "default: low confidence"


@pytest.mark.parametrize(
    "intent",
    [
        "do you remember my preferences?",
        "search your memory for my preferences",
        "what do you know about me?",
    ],
)
async def test_memory_keywords_route_to_memory_specialist(intent: str) -> None:
    # M8: user-facing memory questions route to the Memory specialist (the
    # internal recall agent is no longer a keyword target).
    decision = await router.route(intent=intent, registry=get_registry())
    assert decision.steps[-1].agent_key == MEMORY_AGENT_KEY
