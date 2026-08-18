"""Agent run traces — read-only.

The orchestrator has always persisted a complete trace: one ``agent_runs`` row
per turn, an ``agent_steps`` row per dispatch, and an ``agent_messages`` hop for
every task hand-off, result, and error. None of it had an HTTP surface, so the
data existed and nothing could read it.

Read-only by design. A trace is evidence of what happened; nothing outside the
orchestrator may write one.

Everything is tenant-scoped through the repositories, and the payloads returned
are the previews the orchestrator already stored — intent and reply excerpts,
never a prompt and never reasoning.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import CurrentUserId, DbSession
from app.core.exceptions import AppError
from app.repositories import agent_message_repository as a2a_repo
from app.repositories import agent_run_repository as run_repo
from app.repositories import agent_step_repository as step_repo
from app.repositories import tool_invocation_repository as tool_repo

router = APIRouter(prefix="/runs", tags=["agent-runs"])


class HopResponse(BaseModel):
    """One agent-to-agent message."""

    seq: int
    from_agent: str
    to_agent: str | None = None
    role: str
    payload: dict | None = None
    created_at: str


class StepResponse(BaseModel):
    """One agent dispatch within a run."""

    seq: int
    agent_key: str
    status: str
    # A step records when it was created and when it finished; there is no
    # separate "started" column — creation IS the start.
    created_at: str
    finished_at: str | None = None
    cost_tokens: int = 0
    error: str | None = None


class ToolCallResponse(BaseModel):
    """One tool invocation, as recorded in the audit trail."""

    tool_key: str
    agent_key: str
    tier: str
    decision: str
    status: str
    created_at: str


class RunSummary(BaseModel):
    """A run, without its children."""

    id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    status: str
    route_plan: dict | None = None
    created_at: str


class RunDetail(RunSummary):
    """A run with its full trace."""

    steps: list[StepResponse] = []
    hops: list[HopResponse] = []
    tools: list[ToolCallResponse] = []


@router.get(
    "",
    response_model=list[RunSummary],
    summary="List agent runs for a conversation",
)
async def list_runs(
    user_id: CurrentUserId,
    db: DbSession,
    conversation_id: Annotated[uuid.UUID, Query(description="Conversation to trace.")],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[RunSummary]:
    runs = await run_repo.list_for_conversation(
        db, conversation_id=conversation_id, user_id=user_id, limit=limit
    )
    return [
        RunSummary(
            id=r.id,
            conversation_id=r.conversation_id,
            status=r.status.value,
            route_plan=r.route_plan,
            created_at=r.created_at.isoformat(),
        )
        for r in runs
    ]


@router.get(
    "/{run_id}",
    response_model=RunDetail,
    summary="One run with its steps, agent-to-agent hops, and tool calls",
)
async def get_run(
    run_id: uuid.UUID, user_id: CurrentUserId, db: DbSession
) -> RunDetail:
    run = await run_repo.get_run(db, run_id=run_id, user_id=user_id)
    if run is None:
        # 404 rather than 403 for another tenant's run: the existence of a run
        # id is itself information.
        raise AppError("Run not found.", code="run_not_found", status_code=404)

    steps = await step_repo.list_for_run(db, run_id=run_id, user_id=user_id)
    hops = await a2a_repo.list_for_run(db, run_id=run_id, user_id=user_id)
    tools = await tool_repo.list_for_run(db, run_id=run_id, user_id=user_id)

    return RunDetail(
        id=run.id,
        conversation_id=run.conversation_id,
        status=run.status.value,
        route_plan=run.route_plan,
        created_at=run.created_at.isoformat(),
        steps=[
            StepResponse(
                seq=s.seq,
                agent_key=s.agent_key,
                status=s.status.value,
                created_at=s.created_at.isoformat(),
                finished_at=s.finished_at.isoformat() if s.finished_at else None,
                cost_tokens=s.cost_tokens,
                error=s.error,
            )
            for s in steps
        ],
        hops=[
            HopResponse(
                seq=h.seq,
                from_agent=h.from_agent,
                to_agent=h.to_agent,
                role=h.role.value,
                payload=h.payload,
                created_at=h.created_at.isoformat(),
            )
            for h in hops
        ],
        tools=[
            ToolCallResponse(
                tool_key=t.tool_key,
                agent_key=t.agent_key,
                tier=t.tier.value,
                decision=t.decision.value,
                status=t.status.value,
                created_at=t.created_at.isoformat(),
            )
            for t in tools
        ],
    )
