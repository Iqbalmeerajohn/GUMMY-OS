"""Orchestrator pipeline tests (Phase 3, M5).

Proves: a routed two-step pipeline hands off correctly (the recall digest
reaches the general agent's grounding), costs accumulate per run, the loop
guard halts an injected cycle, and a single-agent intent still routes to
``general`` and matches the M4/legacy behavior.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_run import AgentRun
from app.models.enums import (
    AgentContext,
    MemoryCategory,
    PlanShape,
    RunStatus,
    StepStatus,
)
from app.models.memory import Memory
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
from app.services.conversation import conversation_turn_service as turn_svc
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
    # Cosine DISTANCE ascending (similarity = 1 - distance), so every candidate
    # clears the retrieval relevance floor while still ranking in order.
    return [(memory, 0.1 + 0.1 * index) for index, memory in enumerate(items)]


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


async def _new_conv(db_session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    conv = await conversation_service.create_conversation(
        db_session, user_id=user_id, payload=ConversationCreate()
    )
    return conv.id


async def test_pipeline_hands_off_recall_digest_to_general(
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
        content="Targeting a Qualcomm systems role",
        importance_score=0.9,
        confidence_score=0.9,
    )
    await db_session.commit()

    captured: dict = {}
    fake_llm = FakeLLMProvider(reply="Here is what I remember.")
    original_generate = fake_llm.generate

    async def _spy_generate(**kwargs: object) -> object:
        captured.update(kwargs)
        return await original_generate(**kwargs)

    monkeypatch.setattr(fake_llm, "generate", _spy_generate)

    conv_id = await _new_conv(db_session, seed_user)
    result = await orchestrator_service.orchestrate(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="what do you remember about my career?",
        embedding_service=_embeddings(),
        llm=fake_llm,
        # M8: the recall→general pipeline is now reached via the research-thread
        # hint (the memory *keyword* routes to the Memory specialist instead).
        agent_context=AgentContext.RESEARCH,
    )
    assert result.reply == "Here is what I remember."

    run = (await db_session.execute(select(AgentRun))).scalar_one()
    assert run.status == RunStatus.SUCCEEDED
    assert run.route_plan is not None
    assert run.route_plan["shape"] == PlanShape.PIPELINE.value
    assert run.route_plan["steps"] == [RECALL_AGENT_KEY, GENERAL_AGENT_KEY]

    steps = await step_repo.list_for_run(db_session, run_id=run.id, user_id=seed_user)
    assert [(s.agent_key, s.seq, s.status) for s in steps] == [
        (RECALL_AGENT_KEY, 1, StepStatus.SUCCEEDED),
        (GENERAL_AGENT_KEY, 2, StepStatus.SUCCEEDED),
    ]
    # The recall digest reached the general agent's prompt (hand-off proof).
    prompt_messages = captured["messages"]
    rendered = "\n".join(m["content"] for m in prompt_messages)
    system_text = str(captured.get("system", ""))
    assert "Qualcomm" in (rendered + system_text)
    assert "Relevant stored memories" in (rendered + system_text)
    # Cost accumulated on the run equals the general step's LLM cost
    # (the recall step is free).
    assert run.cost_tokens == result.cost.tokens
    assert result.cost.tokens > 0


async def test_loop_guard_halts_injected_cycle(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )

    async def _cycle_route(**kwargs: object) -> RoutingDecision:
        return RoutingDecision(
            plan_shape=PlanShape.PIPELINE,
            steps=[
                RouteStep(agent_key=RECALL_AGENT_KEY)
                for _ in range(50)  # far beyond the step cap
            ],
            rationale="injected cycle",
            confidence=1.0,
        )

    monkeypatch.setattr(
        "app.services.agents.orchestrator_service.router.route", _cycle_route
    )
    conv_id = await _new_conv(db_session, seed_user)
    with pytest.raises(orchestrator_service.RunBudgetExceededError, match="step cap"):
        await orchestrator_service.orchestrate(
            db_session,
            user_id=seed_user,
            conversation_id=conv_id,
            message="loop forever",
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="never"),
        )
    run = (await db_session.execute(select(AgentRun))).scalar_one()
    assert run.status == RunStatus.FAILED
    assert run.error is not None
    assert "step cap" in run.error


async def test_single_agent_intent_still_matches_legacy(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pipeline support must not disturb the M4 single-agent parity."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    settings = get_settings()

    monkeypatch.setattr(settings, "agents_orchestration_enabled", False)
    conv_legacy = await _new_conv(db_session, seed_user)
    legacy = await turn_svc.run_turn(
        db_session,
        user_id=seed_user,
        conversation_id=conv_legacy,
        message="tell me a fun fact about space",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="Space is big."),
    )

    monkeypatch.setattr(settings, "agents_orchestration_enabled", True)
    conv_orch = await _new_conv(db_session, seed_user)
    orchestrated = await turn_svc.run_turn(
        db_session,
        user_id=seed_user,
        conversation_id=conv_orch,
        message="tell me a fun fact about space",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="Space is big."),
    )

    assert orchestrated.reply == legacy.reply
    assert orchestrated.input_tokens == legacy.input_tokens
    assert orchestrated.output_tokens == legacy.output_tokens

    run = (await db_session.execute(select(AgentRun))).scalar_one()
    assert run.route_plan is not None
    assert run.route_plan["shape"] == PlanShape.SINGLE.value
    assert run.route_plan["steps"] == [GENERAL_AGENT_KEY]
