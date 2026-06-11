"""Run Recorder — trace one orchestration as agent_runs/agent_steps rows.

M3 wraps the existing Phase 2 reply call in a single-agent "general" run so
the turn becomes observable (traced + costed) with **byte-identical
behavior**. All writes are flush-only inside the caller's unit of work, so
the trace commits atomically with the conversation messages. A recorder
failure must never break the turn — callers treat recording as best-effort.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.enums import RunStatus, RunTrigger, StepStatus
from app.repositories import agent_run_repository as run_repo
from app.repositories import agent_step_repository as step_repo

logger = logging.getLogger(__name__)


@dataclass
class RunRecording:
    """An open run + its current step, handed back to the caller to finish."""

    run: AgentRun
    step: AgentStep


# ── Multi-step primitives (M5 pipelines) ──────────────────────────────────────


async def open_run(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    trigger: RunTrigger = RunTrigger.CHAT,
    route_plan: dict | None = None,
) -> AgentRun:
    """Open a ``running`` run with no steps yet (flush-only)."""
    return await run_repo.create_run(
        session,
        user_id=user_id,
        conversation_id=conversation_id,
        trigger=trigger,
        route_plan=route_plan,
    )


async def open_step(
    session: AsyncSession,
    run: AgentRun,
    *,
    agent_key: str,
    input: dict | None = None,
) -> AgentStep:
    """Append a ``running`` step to an open run (seq auto-assigned)."""
    return await step_repo.append_step(
        session,
        run_id=run.id,
        user_id=run.user_id,
        agent_key=agent_key,
        input=input,
    )


async def close_step_success(
    session: AsyncSession,
    run: AgentRun,
    step: AgentStep,
    *,
    output: dict | None = None,
    cost_tokens: int = 0,
    cost_usd: Decimal | float = 0,
) -> None:
    """Finish one step as ``succeeded`` and accumulate its cost on the run."""
    await step_repo.finish_step(
        session,
        step,
        status=StepStatus.SUCCEEDED,
        output=output,
        cost_tokens=cost_tokens,
        cost_usd=cost_usd,
    )
    await run_repo.add_cost(session, run, tokens=cost_tokens, usd=cost_usd)


async def close_step_failure(
    session: AsyncSession,
    step: AgentStep,
    *,
    error: str,
) -> None:
    """Finish one step as ``failed`` (the run's fate is decided separately)."""
    await step_repo.finish_step(
        session, step, status=StepStatus.FAILED, error=error
    )


async def close_run_success(session: AsyncSession, run: AgentRun) -> None:
    """Move an open run to ``succeeded``."""
    await run_repo.set_status(session, run, status=RunStatus.SUCCEEDED)


async def close_run_failure(
    session: AsyncSession, run: AgentRun, *, error: str
) -> None:
    """Move an open run to ``failed`` with its error recorded."""
    await run_repo.set_status(
        session, run, status=RunStatus.FAILED, error=error
    )


# ── Single-step convenience wrappers (the M3 recording path) ──────────────────


async def start_run(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    agent_key: str,
    conversation_id: uuid.UUID | None = None,
    trigger: RunTrigger = RunTrigger.CHAT,
    route_plan: dict | None = None,
    input: dict | None = None,
) -> RunRecording:
    """Open a ``running`` run with its first ``running`` step (flush-only)."""
    run = await run_repo.create_run(
        session,
        user_id=user_id,
        conversation_id=conversation_id,
        trigger=trigger,
        route_plan=route_plan,
    )
    step = await step_repo.append_step(
        session,
        run_id=run.id,
        user_id=user_id,
        agent_key=agent_key,
        input=input,
    )
    return RunRecording(run=run, step=step)


async def finish_success(
    session: AsyncSession,
    recording: RunRecording,
    *,
    output: dict | None = None,
    cost_tokens: int = 0,
    cost_usd: Decimal | float = 0,
) -> None:
    """Close the step and run as ``succeeded``, accumulating cost onto the run."""
    await step_repo.finish_step(
        session,
        recording.step,
        status=StepStatus.SUCCEEDED,
        output=output,
        cost_tokens=cost_tokens,
        cost_usd=cost_usd,
    )
    await run_repo.add_cost(
        session, recording.run, tokens=cost_tokens, usd=cost_usd
    )
    await run_repo.set_status(
        session, recording.run, status=RunStatus.SUCCEEDED
    )


async def finish_failure(
    session: AsyncSession,
    recording: RunRecording,
    *,
    error: str,
) -> None:
    """Close the step and run as ``failed``, recording the error."""
    await step_repo.finish_step(
        session,
        recording.step,
        status=StepStatus.FAILED,
        error=error,
    )
    await run_repo.set_status(
        session, recording.run, status=RunStatus.FAILED, error=error
    )
