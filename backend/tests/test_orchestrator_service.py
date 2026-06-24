"""Orchestrator tests (Phase 3, M4): single-agent run, fallback, parity.

The critical M4 gates:
- parity: with ``agents_orchestration_enabled`` on, the single-agent route
  produces a reply equivalent to ``generate_grounded_reply`` for the same
  input;
- fallback: an orchestrator/handler failure still yields a valid reply via
  the legacy core (the user always gets a reply);
- guards: the per-run step/cost caps halt a run.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.enums import (
    MemoryCategory,
    PlanShape,
    RunStatus,
    StepStatus,
)
from app.models.memory import Memory
from app.repositories import memory_repository as mem_repo
from app.schemas.conversation import ConversationCreate
from app.services.agents import orchestrator_service
from app.services.agents.manifests import GENERAL_AGENT_KEY
from app.services.agents.orchestrator_service import (
    RunBudgetExceededError,
    _RunGuard,
)
from app.services.conversation import conversation_service
from app.services.conversation import conversation_turn_service as turn_svc
from app.services.conversation.conversation_service import (
    ConversationNotFoundError,
)
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
    return [(memory, 0.1 * index) for index, memory in enumerate(items)]


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


async def _new_conv(db_session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    conv = await conversation_service.create_conversation(
        db_session, user_id=user_id, payload=ConversationCreate()
    )
    return conv.id


# ── run guard ─────────────────────────────────────────────────────────────────


def test_run_guard_halts_at_step_cap() -> None:
    guard = _RunGuard(max_steps=1, max_cost_tokens=10_000)
    guard.check_before_dispatch()
    guard.steps = 1
    with pytest.raises(RunBudgetExceededError, match="step cap"):
        guard.check_before_dispatch()


def test_run_guard_halts_at_cost_cap() -> None:
    guard = _RunGuard(max_steps=10, max_cost_tokens=100)
    guard.cost_tokens = 100
    with pytest.raises(RunBudgetExceededError, match="cost cap"):
        guard.check_before_dispatch()


# ── orchestrate (direct) ──────────────────────────────────────────────────────


async def test_orchestrate_single_agent_traced(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    conv_id = await _new_conv(db_session, seed_user)
    result = await orchestrator_service.orchestrate(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="hello there",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="orchestrated hi"),
    )
    assert result.reply == "orchestrated hi"
    assert result.run_id is not None
    assert result.message_metadata == {
        "agent_key": GENERAL_AGENT_KEY,
        "run_id": str(result.run_id),
        "route_shape": "single",
        # A5 routing explanation + B11 web sources (none for the general path).
        "confidence": 0.3,
        "routing_reason": "default: low confidence",
        "web_sources": [],
    }
    assert result.cost.tokens == result.input_tokens + result.output_tokens

    run = (await db_session.execute(select(AgentRun))).scalar_one()
    assert run.status == RunStatus.SUCCEEDED
    assert run.conversation_id == conv_id
    assert run.route_plan is not None
    assert run.route_plan["shape"] == PlanShape.SINGLE.value
    assert run.route_plan["steps"] == [GENERAL_AGENT_KEY]
    step = (await db_session.execute(select(AgentStep))).scalar_one()
    assert step.agent_key == GENERAL_AGENT_KEY
    assert step.status == StepStatus.SUCCEEDED


async def test_orchestrate_records_failure_and_raises(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )

    async def _boom(task: object, *, llm: object) -> object:
        raise RuntimeError("handler exploded")

    monkeypatch.setattr(
        "app.services.agents.handlers.general_agent.handle",
        _boom,
    )
    conv_id = await _new_conv(db_session, seed_user)
    with pytest.raises(RuntimeError, match="handler exploded"):
        await orchestrator_service.orchestrate(
            db_session,
            user_id=seed_user,
            conversation_id=conv_id,
            message="hello",
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="never"),
        )
    run = (await db_session.execute(select(AgentRun))).scalar_one()
    assert run.status == RunStatus.FAILED
    assert run.error == "handler exploded"


# ── run_turn integration (flag on) ────────────────────────────────────────────


async def test_turn_orchestrated_writes_trace_and_persists_messages(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    monkeypatch.setattr(
        get_settings(), "agents_orchestration_enabled", True
    )
    conv_id = await _new_conv(db_session, seed_user)
    result = await turn_svc.run_turn(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="hello",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="hi from orchestrator"),
    )
    assert result.reply == "hi from orchestrator"
    assert result.message_count == 2
    runs = await db_session.scalar(select(func.count()).select_from(AgentRun))
    assert runs == 1


async def test_turn_fallback_on_orchestrator_failure(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kill the handler → the user still gets a (legacy-core) reply."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    monkeypatch.setattr(
        get_settings(), "agents_orchestration_enabled", True
    )

    async def _boom(task: object, *, llm: object) -> object:
        raise RuntimeError("handler exploded")

    monkeypatch.setattr(
        "app.services.agents.handlers.general_agent.handle",
        _boom,
    )
    conv_id = await _new_conv(db_session, seed_user)
    result = await turn_svc.run_turn(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="hello",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="legacy fallback reply"),
    )
    assert result.reply == "legacy fallback reply"
    assert result.message_count == 2  # turn persisted normally
    # The failed run trace committed with the turn (observability).
    run = (await db_session.execute(select(AgentRun))).scalar_one()
    assert run.status == RunStatus.FAILED


async def test_turn_parity_orchestrated_vs_legacy(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE M4 gate: orchestrated reply == legacy reply for the same input."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    await mem_repo.create_memory(
        db_session,
        user_id=seed_user,
        category=MemoryCategory.CAREER,
        content="Preparing for the Qualcomm interview",
        importance_score=0.9,
        confidence_score=0.9,
    )
    await db_session.commit()
    settings = get_settings()

    monkeypatch.setattr(settings, "agents_orchestration_enabled", False)
    conv_legacy = await _new_conv(db_session, seed_user)
    legacy = await turn_svc.run_turn(
        db_session,
        user_id=seed_user,
        conversation_id=conv_legacy,
        message="what am I preparing for?",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="You are preparing for Qualcomm."),
    )

    monkeypatch.setattr(settings, "agents_orchestration_enabled", True)
    conv_orch = await _new_conv(db_session, seed_user)
    orchestrated = await turn_svc.run_turn(
        db_session,
        user_id=seed_user,
        conversation_id=conv_orch,
        message="what am I preparing for?",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="You are preparing for Qualcomm."),
    )

    assert orchestrated.reply == legacy.reply
    assert orchestrated.model == legacy.model
    assert orchestrated.memories_used == legacy.memories_used
    assert orchestrated.input_tokens == legacy.input_tokens
    assert orchestrated.output_tokens == legacy.output_tokens
    assert orchestrated.message_count == legacy.message_count


async def test_foreign_tenant_turn_still_404s_with_flag_on(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    monkeypatch.setattr(
        get_settings(), "agents_orchestration_enabled", True
    )
    conv_id = await _new_conv(db_session, seed_user)
    with pytest.raises(ConversationNotFoundError):
        await turn_svc.run_turn(
            db_session,
            user_id=uuid.uuid4(),  # not the owner
            conversation_id=conv_id,
            message="hello",
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="nope"),
        )
