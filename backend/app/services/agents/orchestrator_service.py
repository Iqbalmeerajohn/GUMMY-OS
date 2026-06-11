"""Master Orchestrator (Phase 3, M4 single-agent → M5 routed pipelines).

The single internal entrypoint for an orchestrated turn:

    route (Router: rules → LLM fallback) → context pack → dispatch each step
    (pipeline hand-off via the pack's scratch) → record run/steps → return a
    reply-shaped ``OrchestrationResult`` that ``run_turn`` persists exactly
    as it persists the legacy reply.

Guards: a per-run step cap and token-cost cap halt runaway pipelines. The
caller (``run_turn``) wraps ``orchestrate`` with the guaranteed fallback to
``generate_grounded_reply`` — an orchestrator error never costs the user a
reply.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import (
    AGENT_MAX_RUN_COST_TOKENS,
    AGENT_MAX_RUN_STEPS,
    AGENT_TRACE_PREVIEW_CHARS,
    DEFAULT_CONTEXT_MAX_MEMORIES,
    DEFAULT_CONTEXT_TOKEN_BUDGET,
)
from app.models.enums import AgentContext
from app.schemas.agents import (
    AgentResult,
    AgentTask,
    CostInfo,
    OrchestrationResult,
    RoutingDecision,
)
from app.services.agents import context_builder, handlers, router, run_recorder
from app.services.agents.registry import get_registry
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class RunBudgetExceededError(RuntimeError):
    """A run hit its step or token-cost cap and was halted."""


class _RunGuard:
    """Per-run step/cost caps (runaway pipeline/cost protection)."""

    def __init__(
        self,
        *,
        max_steps: int = AGENT_MAX_RUN_STEPS,
        max_cost_tokens: int = AGENT_MAX_RUN_COST_TOKENS,
    ) -> None:
        self.max_steps = max_steps
        self.max_cost_tokens = max_cost_tokens
        self.steps = 0
        self.cost_tokens = 0

    def check_before_dispatch(self) -> None:
        if self.steps >= self.max_steps:
            raise RunBudgetExceededError(
                f"run step cap reached ({self.max_steps})"
            )
        if self.cost_tokens >= self.max_cost_tokens:
            raise RunBudgetExceededError(
                f"run cost cap reached ({self.max_cost_tokens} tokens)"
            )

    def record(self, result: AgentResult) -> None:
        self.steps += 1
        self.cost_tokens += result.cost.tokens


async def orchestrate(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message: str,
    embedding_service: EmbeddingService,
    llm: LLMProvider,
    token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET,
    max_memories: int = DEFAULT_CONTEXT_MAX_MEMORIES,
    history: list[dict] | None = None,
    summary: str | None = None,
    agent_context: AgentContext | None = None,
) -> OrchestrationResult:
    """Run one orchestrated turn: routed single-agent or pipeline, traced.

    Flush-only — the caller owns the commit, so the run/step trace lands
    atomically with the conversation messages. Raises on any failure; the
    caller falls back to the legacy reply core.
    """
    settings = get_settings()
    decision: RoutingDecision = await router.route(
        intent=message,
        registry=get_registry(),
        agent_context=agent_context,
        # The LLM classifier is opt-in (cost): rules are deterministic and
        # free, and the general agent is a safe catch-all.
        llm=llm if settings.agents_router_llm_fallback else None,
        fast_model=settings.claude_model_fast,
    )
    route_plan = {
        "shape": decision.plan_shape.value,
        "steps": [s.agent_key for s in decision.steps],
        "rationale": decision.rationale,
        "confidence": decision.confidence,
    }
    run = await run_recorder.open_run(
        session,
        user_id=user_id,
        conversation_id=conversation_id,
        route_plan=route_plan,
    )
    guard = _RunGuard()
    scratch: list[dict] = []
    last_result: AgentResult | None = None
    total_cost = CostInfo()
    proposed_actions: list[dict] = []
    proposed_memories: list[dict] = []
    citations: list[dict] = []
    try:
        # The pack's retrieval is shared across the pipeline (same query);
        # each step sees the prior steps' outputs via scratch.
        base_pack = await context_builder.build(
            session,
            user_id=user_id,
            query=message,
            embedding_service=embedding_service,
            max_memories=max_memories,
            history=history,
            summary=summary,
        )
        for route_step in decision.steps:
            guard.check_before_dispatch()
            step = await run_recorder.open_step(
                session,
                run,
                agent_key=route_step.agent_key,
                input={
                    "message_preview": message[:AGENT_TRACE_PREVIEW_CHARS],
                    "intent": route_step.intent,
                },
            )
            pack = base_pack.model_copy(update={"scratch": list(scratch)})
            task = AgentTask(
                run_id=run.id,
                agent_key=route_step.agent_key,
                intent=route_step.intent or message,
                inputs={
                    "token_budget": token_budget,
                    "max_memories": max_memories,
                },
                context_pack=pack,
            )
            try:
                result = await handlers.dispatch(task, llm=llm)
            except Exception as exc:
                await run_recorder.close_step_failure(
                    session, step, error=str(exc)
                )
                raise
            guard.record(result)
            await run_recorder.close_step_success(
                session,
                run,
                step,
                output=result.output,
                cost_tokens=result.cost.tokens,
                cost_usd=result.cost.usd,
            )
            scratch.append(
                {"agent_key": route_step.agent_key, "output": result.output}
            )
            last_result = result
            total_cost = CostInfo(
                tokens=total_cost.tokens + result.cost.tokens,
                usd=total_cost.usd + result.cost.usd,
            )
            # Proposals accumulate across the whole pipeline, not just the
            # terminal step; persistence happens post-commit via the
            # agent_memory facade (M7), never inside this transaction.
            proposed_actions.extend(result.proposed_actions)
            proposed_memories.extend(result.proposed_memories)
            citations.extend(result.citations)
    except Exception as exc:
        await run_recorder.close_run_failure(session, run, error=str(exc))
        raise

    if last_result is None:  # defensive: an empty route plan is a bug
        await run_recorder.close_run_failure(
            session, run, error="empty route plan"
        )
        raise RuntimeError("router produced an empty route plan")

    await run_recorder.close_run_success(session, run)
    reply = str(last_result.output.get("reply", ""))
    return OrchestrationResult(
        reply=reply,
        run_id=run.id,
        proposed_actions=proposed_actions,
        proposed_memories=proposed_memories,
        citations=citations,
        cost=total_cost,
        message_metadata={
            "agent_key": decision.steps[-1].agent_key,
            "run_id": str(run.id),
            "route_shape": decision.plan_shape.value,
        },
        model=str(last_result.output.get("model", "")),
        memories_used=int(last_result.output.get("memories_used", 0)),
        input_tokens=int(last_result.output.get("input_tokens", 0)),
        output_tokens=int(last_result.output.get("output_tokens", 0)),
    )
