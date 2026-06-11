"""Run-recorder tests (Phase 3, M3).

Proves: a flag-on turn writes exactly one run + one step (committed
atomically with the messages, correct status/cost); a flag-off turn writes
nothing; and the reply is **identical** with recording on vs off (parity —
the M3 gate).
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
    MessageRole,
    RunStatus,
    StepStatus,
)
from app.models.memory import Memory
from app.repositories import agent_step_repository as step_repo
from app.repositories import memory_repository as mem_repo
from app.repositories import message_repository as msg_repo
from app.schemas.conversation import ConversationCreate
from app.services.agents import run_recorder
from app.services.agents.manifests import GENERAL_AGENT_KEY
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


async def _run_and_step_counts(session: AsyncSession) -> tuple[int, int]:
    runs = await session.scalar(select(func.count()).select_from(AgentRun))
    steps = await session.scalar(select(func.count()).select_from(AgentStep))
    return int(runs or 0), int(steps or 0)


# ── recorder unit behavior ────────────────────────────────────────────────────


async def test_start_and_finish_success(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    recording = await run_recorder.start_run(
        db_session,
        user_id=seed_user,
        agent_key=GENERAL_AGENT_KEY,
        input={"message_preview": "hi"},
    )
    assert recording.run.status == RunStatus.RUNNING
    assert recording.step.seq == 1
    await run_recorder.finish_success(
        db_session,
        recording,
        output={"reply_preview": "hello"},
        cost_tokens=42,
    )
    assert recording.step.status == StepStatus.SUCCEEDED
    assert recording.step.finished_at is not None
    assert recording.run.status == RunStatus.SUCCEEDED
    assert recording.run.cost_tokens == 42
    assert recording.run.finished_at is not None


async def test_finish_failure_records_error(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    recording = await run_recorder.start_run(
        db_session, user_id=seed_user, agent_key=GENERAL_AGENT_KEY
    )
    await run_recorder.finish_failure(
        db_session, recording, error="llm timeout"
    )
    assert recording.step.status == StepStatus.FAILED
    assert recording.step.error == "llm timeout"
    assert recording.run.status == RunStatus.FAILED
    assert recording.run.error == "llm timeout"


# ── flag-gated turn integration ───────────────────────────────────────────────


async def test_flag_off_turn_writes_no_trace(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    monkeypatch.setattr(get_settings(), "agents_run_recording", False)
    conv_id = await _new_conv(db_session, seed_user)
    await turn_svc.run_turn(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="hello",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="hi there"),
    )
    assert await _run_and_step_counts(db_session) == (0, 0)


async def test_flag_on_turn_writes_one_run_one_step(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    monkeypatch.setattr(get_settings(), "agents_run_recording", True)
    conv_id = await _new_conv(db_session, seed_user)
    result = await turn_svc.run_turn(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="hello",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="hi there"),
    )
    assert await _run_and_step_counts(db_session) == (1, 1)

    run = (await db_session.execute(select(AgentRun))).scalar_one()
    assert run.user_id == seed_user
    assert run.conversation_id == conv_id
    assert run.status == RunStatus.SUCCEEDED
    assert run.cost_tokens == result.input_tokens + result.output_tokens

    steps = await step_repo.list_for_run(
        db_session, run_id=run.id, user_id=seed_user
    )
    assert len(steps) == 1
    step = steps[0]
    assert step.agent_key == GENERAL_AGENT_KEY
    assert step.status == StepStatus.SUCCEEDED
    assert step.input == {"message_preview": "hello"}
    assert step.output is not None
    assert step.output["reply_preview"] == result.reply[:200]

    # The messages persisted exactly as the unrecorded path persists them.
    messages, total = await msg_repo.list_messages(
        db_session,
        conversation_id=conv_id,
        user_id=seed_user,
        limit=10,
        offset=0,
    )
    assert total == 2
    assert [m.role for m in messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]


async def test_parity_reply_identical_flag_on_vs_off(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The M3 gate: recording must not change the reply or its accounting."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    settings = get_settings()

    monkeypatch.setattr(settings, "agents_run_recording", False)
    conv_off = await _new_conv(db_session, seed_user)
    off = await turn_svc.run_turn(
        db_session,
        user_id=seed_user,
        conversation_id=conv_off,
        message="what am I preparing for?",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="You are preparing for Qualcomm."),
    )

    monkeypatch.setattr(settings, "agents_run_recording", True)
    conv_on = await _new_conv(db_session, seed_user)
    on = await turn_svc.run_turn(
        db_session,
        user_id=seed_user,
        conversation_id=conv_on,
        message="what am I preparing for?",
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="You are preparing for Qualcomm."),
    )

    assert on.reply == off.reply
    assert on.model == off.model
    assert on.memories_used == off.memories_used
    assert on.input_tokens == off.input_tokens
    assert on.output_tokens == off.output_tokens
    assert on.message_count == off.message_count
