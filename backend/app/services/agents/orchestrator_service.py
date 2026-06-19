"""Master Orchestrator (Phase 3: M4 single → M5 pipeline → M9 parallel).

The single internal entrypoint for an orchestrated turn:

    route (Router) → context pack → execute the plan
      · single/pipeline: steps in order, scratch hand-off between steps
      · parallel: fan-out concurrently, failures isolated per branch, gather
    → compose (Personality hook last) → return a reply-shaped
    ``OrchestrationResult`` that ``run_turn`` persists like the legacy reply.

Every orchestration is traced: one ``agent_runs`` row, one ``agent_steps``
row per dispatch, and an ``agent_messages`` hop for every task hand-off and
result/error — the complete A2A audit trail (M9). All DB writes happen
sequentially on the turn's session; only the **pure** agent handlers run
concurrently in the parallel shape.

Guards: a per-run step cap and token-cost cap halt runaway plans. The caller
(``run_turn``) wraps ``orchestrate`` with the guaranteed fallback to
``generate_grounded_reply`` — an orchestrator error never costs the user a
reply.
"""

from __future__ import annotations

import asyncio
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
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.enums import AgentContext, AgentMessageRole, PlanShape
from app.repositories import agent_message_repository as a2a_repo
from app.schemas.agents import (
    AgentResult,
    AgentTask,
    ContextPack,
    CostInfo,
    OrchestrationResult,
    RoutingDecision,
)
from app.services.agents import (
    compose,
    context_builder,
    handlers,
    router,
    run_recorder,
)
from app.services.agents.registry import get_registry
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# The Orchestrator's name on the A2A trace (it is not an agent).
ORCHESTRATOR_ACTOR = "orchestrator"


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

    def check_before_dispatch(self, branch_count: int = 1) -> None:
        if self.steps + branch_count > self.max_steps:
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


def _make_task(
    *,
    run_id: uuid.UUID,
    agent_key: str,
    intent: str,
    base_pack: ContextPack,
    scratch: list[dict],
    token_budget: int,
    max_memories: int,
    user_identity: str | None = None,
) -> AgentTask:
    return AgentTask(
        run_id=run_id,
        agent_key=agent_key,
        intent=intent,
        inputs={
            "token_budget": token_budget,
            "max_memories": max_memories,
            # Authenticated profile block shared with every agent's prompt.
            "user_identity": user_identity,
        },
        context_pack=base_pack.model_copy(update={"scratch": list(scratch)}),
    )


async def _record_task_hop(
    session: AsyncSession, run: AgentRun, *, agent_key: str, intent: str
) -> None:
    await a2a_repo.append_message(
        session,
        run_id=run.id,
        user_id=run.user_id,
        from_agent=ORCHESTRATOR_ACTOR,
        to_agent=agent_key,
        role=AgentMessageRole.TASK,
        payload={"intent_preview": intent[:AGENT_TRACE_PREVIEW_CHARS]},
    )


async def _record_result_hop(
    session: AsyncSession,
    run: AgentRun,
    *,
    agent_key: str,
    result: AgentResult,
) -> None:
    reply = str(result.output.get("reply", ""))
    await a2a_repo.append_message(
        session,
        run_id=run.id,
        user_id=run.user_id,
        from_agent=agent_key,
        to_agent=None,
        role=AgentMessageRole.RESULT,
        payload={
            "reply_preview": reply[:AGENT_TRACE_PREVIEW_CHARS],
            "output_keys": sorted(result.output.keys()),
            "cost_tokens": result.cost.tokens,
        },
    )


async def _record_error_hop(
    session: AsyncSession, run: AgentRun, *, agent_key: str, error: str
) -> None:
    await a2a_repo.append_message(
        session,
        run_id=run.id,
        user_id=run.user_id,
        from_agent=agent_key,
        to_agent=None,
        role=AgentMessageRole.ERROR,
        payload={"error": error[:AGENT_TRACE_PREVIEW_CHARS]},
    )


async def _run_sequential(
    session: AsyncSession,
    *,
    run: AgentRun,
    decision: RoutingDecision,
    base_pack: ContextPack,
    guard: _RunGuard,
    message: str,
    llm: LLMProvider,
    token_budget: int,
    max_memories: int,
    user_identity: str | None = None,
) -> list[tuple[str, AgentResult]]:
    """Single/pipeline execution: steps in order, scratch handed forward.

    A step failure aborts the run (the caller's fallback guarantees the
    user still gets a reply).
    """
    results: list[tuple[str, AgentResult]] = []
    scratch: list[dict] = []
    for route_step in decision.steps:
        guard.check_before_dispatch()
        intent = route_step.intent or message
        step = await run_recorder.open_step(
            session,
            run,
            agent_key=route_step.agent_key,
            input={
                "message_preview": message[:AGENT_TRACE_PREVIEW_CHARS],
                "intent": route_step.intent,
            },
        )
        await _record_task_hop(
            session, run, agent_key=route_step.agent_key, intent=intent
        )
        task = _make_task(
            run_id=run.id,
            agent_key=route_step.agent_key,
            intent=intent,
            base_pack=base_pack,
            scratch=scratch,
            token_budget=token_budget,
            max_memories=max_memories,
            user_identity=user_identity,
        )
        try:
            result = await handlers.dispatch(task, llm=llm)
        except Exception as exc:
            await run_recorder.close_step_failure(
                session, step, error=str(exc)
            )
            await _record_error_hop(
                session, run, agent_key=route_step.agent_key, error=str(exc)
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
        await _record_result_hop(
            session, run, agent_key=route_step.agent_key, result=result
        )
        scratch.append(
            {"agent_key": route_step.agent_key, "output": result.output}
        )
        results.append((route_step.agent_key, result))
    return results


async def _run_parallel(
    session: AsyncSession,
    *,
    run: AgentRun,
    decision: RoutingDecision,
    base_pack: ContextPack,
    guard: _RunGuard,
    message: str,
    llm: LLMProvider,
    token_budget: int,
    max_memories: int,
    user_identity: str | None = None,
) -> list[tuple[str, AgentResult]]:
    """Parallel fan-out/gather: branches run concurrently, failures are
    isolated per branch; the run succeeds if at least one branch does.

    DB writes stay sequential on the shared session — only the pure
    handlers run concurrently.
    """
    guard.check_before_dispatch(branch_count=len(decision.steps))

    # (agent_key, intent, step)
    branches: list[tuple[str, str, AgentStep]] = []
    for route_step in decision.steps:
        intent = route_step.intent or message
        step = await run_recorder.open_step(
            session,
            run,
            agent_key=route_step.agent_key,
            input={
                "message_preview": message[:AGENT_TRACE_PREVIEW_CHARS],
                "intent": route_step.intent,
                "parallel": True,
            },
        )
        await _record_task_hop(
            session, run, agent_key=route_step.agent_key, intent=intent
        )
        branches.append((route_step.agent_key, intent, step))

    tasks = [
        handlers.dispatch(
            _make_task(
                run_id=run.id,
                agent_key=agent_key,
                intent=intent,
                base_pack=base_pack,
                scratch=[],
                token_budget=token_budget,
                max_memories=max_memories,
                user_identity=user_identity,
            ),
            llm=llm,
        )
        for agent_key, intent, _ in branches
    ]
    outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[tuple[str, AgentResult]] = []
    errors: list[str] = []
    for (agent_key, _intent, step), outcome in zip(
        branches, outcomes, strict=True
    ):
        if isinstance(outcome, BaseException):
            error = str(outcome)
            await run_recorder.close_step_failure(session, step, error=error)
            await _record_error_hop(
                session, run, agent_key=agent_key, error=error
            )
            errors.append(f"{agent_key}: {error}")
            continue
        guard.record(outcome)
        await run_recorder.close_step_success(
            session,
            run,
            step,
            output=outcome.output,
            cost_tokens=outcome.cost.tokens,
            cost_usd=outcome.cost.usd,
        )
        await _record_result_hop(
            session, run, agent_key=agent_key, result=outcome
        )
        results.append((agent_key, outcome))

    if not results:
        raise RuntimeError(
            f"all parallel branches failed: {'; '.join(errors)}"
        )
    if errors:
        logger.warning(
            "parallel run %s: %d branch(es) failed, composing from %d",
            run.id,
            len(errors),
            len(results),
        )
    return results


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
    user_identity: str | None = None,
) -> OrchestrationResult:
    """Run one orchestrated turn (routed single | pipeline | parallel).

    Flush-only — the caller owns the commit, so the run/step/hop trace lands
    atomically with the conversation messages. Raises on total failure; the
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
    try:
        base_pack = await context_builder.build(
            session,
            user_id=user_id,
            query=message,
            embedding_service=embedding_service,
            max_memories=max_memories,
            history=history,
            summary=summary,
        )
        runner = (
            _run_parallel
            if decision.plan_shape == PlanShape.PARALLEL
            else _run_sequential
        )
        results = await runner(
            session,
            run=run,
            decision=decision,
            base_pack=base_pack,
            guard=guard,
            message=message,
            llm=llm,
            token_budget=token_budget,
            max_memories=max_memories,
            user_identity=user_identity,
        )
        if not results:  # defensive: an empty route plan is a bug
            raise RuntimeError("router produced an empty route plan")
    except Exception as exc:
        await run_recorder.close_run_failure(session, run, error=str(exc))
        raise

    await run_recorder.close_run_success(session, run)

    reply = compose.compose_reply(decision.plan_shape, results)
    last_result = results[-1][1]
    total_cost = CostInfo(
        tokens=sum(r.cost.tokens for _, r in results),
        usd=sum(r.cost.usd for _, r in results),
    )
    if decision.plan_shape == PlanShape.PARALLEL:
        input_tokens = sum(
            int(r.output.get("input_tokens", 0)) for _, r in results
        )
        output_tokens = sum(
            int(r.output.get("output_tokens", 0)) for _, r in results
        )
        model = next(
            (
                str(r.output["model"])
                for _, r in results
                if r.output.get("model")
            ),
            "",
        )
        memories_used = max(
            (int(r.output.get("memories_used", 0)) for _, r in results),
            default=0,
        )
    else:
        input_tokens = int(last_result.output.get("input_tokens", 0))
        output_tokens = int(last_result.output.get("output_tokens", 0))
        model = str(last_result.output.get("model", ""))
        memories_used = int(last_result.output.get("memories_used", 0))

    return OrchestrationResult(
        reply=reply,
        run_id=run.id,
        proposed_actions=[
            action for _, r in results for action in r.proposed_actions
        ],
        proposed_memories=[
            memory for _, r in results for memory in r.proposed_memories
        ],
        citations=[c for _, r in results for c in r.citations],
        cost=total_cost,
        message_metadata={
            "agent_key": results[-1][0],
            "run_id": str(run.id),
            "route_shape": decision.plan_shape.value,
        },
        model=model,
        memories_used=memories_used,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
