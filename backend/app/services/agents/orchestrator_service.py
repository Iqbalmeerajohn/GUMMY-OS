"""Master Orchestrator (Phase 3, M4 — single-agent).

The single internal entrypoint for an orchestrated turn. M4 shape: build a
context pack, dispatch the one ``general`` agent, record the run/steps, and
return a reply-shaped ``OrchestrationResult`` that ``run_turn`` persists
exactly as it persists the legacy reply. Routing (M5), tools (M6), memory
writes (M7), and parallel compose (M9) extend this service without changing
its contract.

Guards: a per-run step cap and token-cost cap (loop/cost protection). The
caller (``run_turn``) wraps ``orchestrate`` with the guaranteed fallback to
``generate_grounded_reply`` — an orchestrator error never costs the user a
reply.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    AGENT_MAX_RUN_COST_TOKENS,
    AGENT_MAX_RUN_STEPS,
    AGENT_TRACE_PREVIEW_CHARS,
    DEFAULT_CONTEXT_MAX_MEMORIES,
    DEFAULT_CONTEXT_TOKEN_BUDGET,
)
from app.models.enums import PlanShape
from app.schemas.agents import (
    AgentResult,
    AgentTask,
    ContextPack,
    CostInfo,
    OrchestrationResult,
)
from app.services.agents import context_builder, run_recorder
from app.services.agents.handlers import general_agent
from app.services.agents.manifests import GENERAL_AGENT_KEY
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class RunBudgetExceededError(RuntimeError):
    """A run hit its step or token-cost cap and was halted."""


class _RunGuard:
    """Per-run step/cost caps (meaningful for M5+ pipelines; enforced now)."""

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
) -> OrchestrationResult:
    """Run one orchestrated turn (M4: single general agent, traced).

    Flush-only — the caller owns the commit, so the run/step trace lands
    atomically with the conversation messages. Raises on any failure; the
    caller falls back to the legacy reply core.
    """
    route_plan = {
        "shape": PlanShape.SINGLE.value,
        "steps": [GENERAL_AGENT_KEY],
        "rationale": "M4 single-agent orchestration (router lands in M5)",
    }
    recording = await run_recorder.start_run(
        session,
        user_id=user_id,
        agent_key=GENERAL_AGENT_KEY,
        conversation_id=conversation_id,
        route_plan=route_plan,
        input={"message_preview": message[:AGENT_TRACE_PREVIEW_CHARS]},
    )
    guard = _RunGuard()
    try:
        pack: ContextPack = await context_builder.build(
            session,
            user_id=user_id,
            query=message,
            embedding_service=embedding_service,
            max_memories=max_memories,
            history=history,
            summary=summary,
        )
        task = AgentTask(
            run_id=recording.run.id,
            agent_key=GENERAL_AGENT_KEY,
            intent=message,
            inputs={
                "token_budget": token_budget,
                "max_memories": max_memories,
            },
            context_pack=pack,
        )
        guard.check_before_dispatch()
        result = await general_agent.handle(task, llm=llm)
        guard.record(result)
    except Exception as exc:
        await run_recorder.finish_failure(session, recording, error=str(exc))
        raise

    reply = str(result.output.get("reply", ""))
    await run_recorder.finish_success(
        session,
        recording,
        output={
            "reply_preview": reply[:AGENT_TRACE_PREVIEW_CHARS],
            "model": result.output.get("model"),
            "memories_used": result.output.get("memories_used"),
        },
        cost_tokens=result.cost.tokens,
    )
    return OrchestrationResult(
        reply=reply,
        run_id=recording.run.id,
        proposed_actions=result.proposed_actions,
        proposed_memories=result.proposed_memories,
        citations=result.citations,
        cost=CostInfo(tokens=result.cost.tokens, usd=result.cost.usd),
        message_metadata={
            "agent_key": GENERAL_AGENT_KEY,
            "run_id": str(recording.run.id),
        },
        model=str(result.output.get("model", "")),
        memories_used=int(result.output.get("memories_used", 0)),
        input_tokens=int(result.output.get("input_tokens", 0)),
        output_tokens=int(result.output.get("output_tokens", 0)),
    )
