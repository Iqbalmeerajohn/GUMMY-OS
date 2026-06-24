"""Agent execution tests (Phase 3, M8): route → execute → compose.

The orchestrator is the M8 executor: it routes (Auto or manual override),
dispatches the chosen agent through the M7-grounded handler, composes the reply,
and emits the agent analytics family. These tests pin specialist routing, manual
override, the persisted reply attribution, and the analytics events.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_run import AgentRun
from app.models.enums import MemoryCategory
from app.models.memory import Memory
from app.models.message import Message
from app.repositories import memory_repository as mem_repo
from app.schemas.conversation import ConversationCreate
from app.services.agents import orchestrator_service
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
    return [(memory, 0.1 * index) for index, memory in enumerate(items)]


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


async def _new_conv(db_session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    conv = await conversation_service.create_conversation(
        db_session, user_id=user_id, payload=ConversationCreate()
    )
    return conv.id


async def test_orchestrate_routes_to_specialist(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    conv_id = await _new_conv(db_session, seed_user)
    result = await orchestrator_service.orchestrate(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="Review my resume and the jobs I should apply for",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="career advice"),
    )
    assert (result.message_metadata or {})["agent_key"] == "career"
    run = (await db_session.execute(select(AgentRun))).scalar_one()
    assert (run.route_plan or {})["steps"] == ["career"]


async def test_orchestrate_manual_override_wins(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    conv_id = await _new_conv(db_session, seed_user)
    # A career-shaped message, but Research is pinned.
    result = await orchestrator_service.orchestrate(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="review my resume",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="research output"),
        agent_key="research",
    )
    assert (result.message_metadata or {})["agent_key"] == "research"


async def test_orchestrate_emits_agent_analytics(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    events: list[str] = []
    monkeypatch.setattr(
        "app.observability.analytics.capture_event",
        lambda *, distinct_id, event, properties=None: events.append(event),
    )
    conv_id = await _new_conv(db_session, seed_user)
    await orchestrator_service.orchestrate(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="Teach me transformers",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="lesson"),
    )
    assert "AgentSelected" in events
    assert "AgentExecuted" in events


async def test_orchestrate_override_emits_override_event(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    events: list[str] = []
    monkeypatch.setattr(
        "app.observability.analytics.capture_event",
        lambda *, distinct_id, event, properties=None: events.append(event),
    )
    conv_id = await _new_conv(db_session, seed_user)
    await orchestrator_service.orchestrate(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="hello",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="x"),
        agent_key="planner",
    )
    assert "AgentOverride" in events


async def test_run_turn_persists_agent_on_assistant_message(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    monkeypatch.setattr(get_settings(), "agents_orchestration_enabled", True)
    conv_id = await _new_conv(db_session, seed_user)
    result = await turn_svc.run_turn(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="Compare AI Engineer vs Data Engineer",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="comparison"),
    )
    msg = (
        await db_session.execute(
            select(Message).where(Message.id == result.assistant_message_id)
        )
    ).scalar_one()
    assert msg.extra_metadata is not None
    assert msg.extra_metadata["agent_key"] == "research"
