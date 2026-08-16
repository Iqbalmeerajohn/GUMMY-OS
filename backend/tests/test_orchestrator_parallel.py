"""Parallel orchestration + A2A trace tests (Phase 3, M9).

Proves: fan-out runs branches concurrently and gathers a composed reply;
``agent_messages`` records every hop in order (task/result/error); a failing
branch is isolated (run still composes from the survivors); the sequential
shapes also write the hop trail; and all-branches-failed raises (so the
turn's fallback fires).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentRun
from app.models.enums import (
    AgentContext,
    AgentMessageRole,
    MemoryCategory,
    PlanShape,
    RunStatus,
    StepStatus,
)
from app.models.memory import Memory
from app.repositories import agent_message_repository as a2a_repo
from app.repositories import agent_step_repository as step_repo
from app.repositories import memory_repository as mem_repo
from app.schemas.agents import RouteStep, RoutingDecision
from app.schemas.conversation import ConversationCreate
from app.services.agents import orchestrator_service
from app.services.agents.manifests import (
    GENERAL_AGENT_KEY,
    RECALL_AGENT_KEY,
)
from app.services.conversation import conversation_service
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.llm.fake_provider import FakeLLMProvider


async def _fake_search(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query_vector: list[float],
    embedding_model: str,
    limit: int,
    include_archived: bool = False,
    category: MemoryCategory | None = None,
) -> list[tuple[Memory, float]]:
    items, _ = await mem_repo.list_memories(
        session, user_id=user_id, limit=limit, offset=0
    )
    return [(memory, 0.8) for memory in items]


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


async def _new_conv(db_session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    conv = await conversation_service.create_conversation(
        db_session, user_id=user_id, payload=ConversationCreate()
    )
    return conv.id


def _parallel_route(*keys: str) -> RoutingDecision:
    return RoutingDecision(
        plan_shape=PlanShape.PARALLEL,
        steps=[RouteStep(agent_key=key) for key in keys],
        rationale="injected parallel",
        confidence=1.0,
    )


def _route_patch(monkeypatch: pytest.MonkeyPatch, decision: RoutingDecision) -> None:
    async def _fixed_route(**kwargs: object) -> RoutingDecision:
        return decision

    monkeypatch.setattr(
        "app.services.agents.orchestrator_service.router.route", _fixed_route
    )


async def test_parallel_fan_out_gathers_and_traces(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    await mem_repo.create_memory(
        db_session,
        user_id=seed_user,
        category=MemoryCategory.CAREER,
        content="Qualcomm prep",
        importance_score=0.9,
        confidence_score=0.9,
    )
    await db_session.commit()
    _route_patch(monkeypatch, _parallel_route(RECALL_AGENT_KEY, GENERAL_AGENT_KEY))

    conv_id = await _new_conv(db_session, seed_user)
    result = await orchestrator_service.orchestrate(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="parallel please",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="general says hi"),
    )
    # Both branches contributed → labeled deterministic merge.
    assert f"[{RECALL_AGENT_KEY}]" in result.reply
    assert f"[{GENERAL_AGENT_KEY}]" in result.reply
    assert "general says hi" in result.reply
    assert result.message_metadata is not None
    assert result.message_metadata["route_shape"] == "parallel"

    run = (await db_session.execute(select(AgentRun))).scalar_one()
    assert run.status == RunStatus.SUCCEEDED
    steps = await step_repo.list_for_run(db_session, run_id=run.id, user_id=seed_user)
    assert {s.agent_key for s in steps} == {
        RECALL_AGENT_KEY,
        GENERAL_AGENT_KEY,
    }
    assert all(s.status == StepStatus.SUCCEEDED for s in steps)

    # The A2A trail: 2 task hops then 2 result hops, seq strictly ordered.
    hops = await a2a_repo.list_for_run(db_session, run_id=run.id, user_id=seed_user)
    assert [h.seq for h in hops] == [1, 2, 3, 4]
    assert [h.role for h in hops] == [
        AgentMessageRole.TASK,
        AgentMessageRole.TASK,
        AgentMessageRole.RESULT,
        AgentMessageRole.RESULT,
    ]
    assert hops[0].from_agent == orchestrator_service.ORCHESTRATOR_ACTOR
    assert {hops[0].to_agent, hops[1].to_agent} == {
        RECALL_AGENT_KEY,
        GENERAL_AGENT_KEY,
    }


async def test_parallel_branches_run_concurrently(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two slow branches overlap in time (true fan-out, not serial)."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    in_flight = 0
    max_in_flight = 0

    async def _slow_handle(task: object, **kwargs: object) -> object:
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        from app.schemas.agents import AgentResult

        return AgentResult(output={"reply": "slow"})

    monkeypatch.setattr(
        "app.services.agents.handlers.general_agent.handle", _slow_handle
    )
    monkeypatch.setattr(
        "app.services.agents.handlers.recall_agent.handle", _slow_handle
    )
    _route_patch(monkeypatch, _parallel_route(RECALL_AGENT_KEY, GENERAL_AGENT_KEY))
    conv_id = await _new_conv(db_session, seed_user)
    await orchestrator_service.orchestrate(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="overlap?",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="x"),
    )
    assert max_in_flight == 2  # both branches were in flight together


async def test_parallel_failing_branch_isolated(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )

    async def _boom(task: object, **kwargs: object) -> object:
        raise RuntimeError("branch exploded")

    monkeypatch.setattr("app.services.agents.handlers.recall_agent.handle", _boom)
    _route_patch(monkeypatch, _parallel_route(RECALL_AGENT_KEY, GENERAL_AGENT_KEY))
    conv_id = await _new_conv(db_session, seed_user)
    result = await orchestrator_service.orchestrate(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="one branch dies",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="survivor reply"),
    )
    # The run still composed a reply from the surviving branch.
    assert result.reply == "survivor reply"

    run = (await db_session.execute(select(AgentRun))).scalar_one()
    assert run.status == RunStatus.SUCCEEDED
    steps = await step_repo.list_for_run(db_session, run_id=run.id, user_id=seed_user)
    by_key = {s.agent_key: s for s in steps}
    assert by_key[RECALL_AGENT_KEY].status == StepStatus.FAILED
    assert by_key[RECALL_AGENT_KEY].error == "branch exploded"
    assert by_key[GENERAL_AGENT_KEY].status == StepStatus.SUCCEEDED

    hops = await a2a_repo.list_for_run(db_session, run_id=run.id, user_id=seed_user)
    roles = [h.role for h in hops]
    assert roles.count(AgentMessageRole.TASK) == 2
    assert AgentMessageRole.ERROR in roles
    assert AgentMessageRole.RESULT in roles


async def test_parallel_all_branches_failed_raises(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )

    async def _boom(task: object, **kwargs: object) -> object:
        raise RuntimeError("dead")

    monkeypatch.setattr("app.services.agents.handlers.recall_agent.handle", _boom)
    monkeypatch.setattr("app.services.agents.handlers.general_agent.handle", _boom)
    _route_patch(monkeypatch, _parallel_route(RECALL_AGENT_KEY, GENERAL_AGENT_KEY))
    conv_id = await _new_conv(db_session, seed_user)
    with pytest.raises(RuntimeError, match="all parallel branches failed"):
        await orchestrator_service.orchestrate(
            db_session,
            user_id=seed_user,
            conversation_id=conv_id,
            message="everything dies",
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="never"),
        )
    run = (await db_session.execute(select(AgentRun))).scalar_one()
    assert run.status == RunStatus.FAILED


async def test_parallel_step_cap_enforced_before_fan_out(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    _route_patch(monkeypatch, _parallel_route(*([RECALL_AGENT_KEY] * 50)))
    conv_id = await _new_conv(db_session, seed_user)
    with pytest.raises(orchestrator_service.RunBudgetExceededError, match="step cap"):
        await orchestrator_service.orchestrate(
            db_session,
            user_id=seed_user,
            conversation_id=conv_id,
            message="too wide",
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="never"),
        )


async def test_sequential_shapes_also_write_hop_trail(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    conv_id = await _new_conv(db_session, seed_user)
    await orchestrator_service.orchestrate(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="what do you remember about me?",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="pipeline reply"),
        # M8: reach the recall→general pipeline via the research-thread hint (the
        # memory keyword now routes to the Memory specialist).
        agent_context=AgentContext.RESEARCH,
    )
    run = (await db_session.execute(select(AgentRun))).scalar_one()
    hops = await a2a_repo.list_for_run(db_session, run_id=run.id, user_id=seed_user)
    # task→result for recall, then task→result for general, in seq order.
    assert [(h.role, h.from_agent) for h in hops] == [
        (AgentMessageRole.TASK, orchestrator_service.ORCHESTRATOR_ACTOR),
        (AgentMessageRole.RESULT, RECALL_AGENT_KEY),
        (AgentMessageRole.TASK, orchestrator_service.ORCHESTRATOR_ACTOR),
        (AgentMessageRole.RESULT, GENERAL_AGENT_KEY),
    ]
