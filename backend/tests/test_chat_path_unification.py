"""The streamed turn and the non-streamed turn are one pipeline.

Before this, ``stream_turn`` had its own copy of routing, persona assembly, and
search fusion, while ``run_turn`` used the Master Orchestrator. The UI only ever
called the streamed endpoint, so the orchestrator — with its plan shapes, agent
trace, and proposed memories — never actually ran in production, and the two
copies drifted (M8.5 shipped formatting rules to only one of them).

These tests assert the property that was previously unguarded: **both endpoints
run the same orchestration**, and the streamed turn produces the same agent
attribution, trace, and accounting as the non-streamed one.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory, MessageRole
from app.models.memory import Memory
from app.repositories import agent_run_repository as run_repo
from app.repositories import memory_repository as mem_repo
from app.repositories import message_repository as msg_repo
from app.schemas.conversation import ConversationCreate
from app.services.conversation import conversation_service
from app.services.conversation import conversation_turn_service as turn_svc
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.llm.fake_provider import FakeLLMProvider


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


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
    # Cosine DISTANCE: 0.2 → similarity 0.8, above the relevance floor.
    return [(memory, 0.2) for memory in items]


async def _new_conv(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    conv = await conversation_service.create_conversation(
        session, user_id=user_id, payload=ConversationCreate()
    )
    return conv.id


async def _seed(session: AsyncSession, user_id: uuid.UUID) -> None:
    await mem_repo.create_memory(
        session,
        user_id=user_id,
        category=MemoryCategory.CAREER,
        content="Preparing for the Qualcomm interview",
        importance_score=0.9,
        confidence_score=0.9,
    )
    await session.commit()


async def _drain(agen: AsyncIterator[dict]) -> list[dict]:
    return [event async for event in agen]


async def test_streamed_turn_runs_the_orchestrator(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression that mattered: the UI's endpoint records an agent run.

    An ``agent_runs`` row is the proof that orchestration executed — the old
    streamed path produced none, because it never reached the orchestrator.
    """
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _seed(db_session, seed_user)
    conversation_id = await _new_conv(db_session, seed_user)

    await _drain(
        turn_svc.stream_turn(
            db_session,
            user_id=seed_user,
            conversation_id=conversation_id,
            message="what am I preparing for?",
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="Qualcomm."),
        )
    )

    runs = await run_repo.list_for_conversation(
        db_session, conversation_id=conversation_id, user_id=seed_user, limit=10
    )
    assert len(runs) == 1
    assert runs[0].conversation_id == conversation_id


async def test_streamed_turn_emits_deltas_then_exactly_one_done(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Streaming is preserved: the event contract is unchanged for the client."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _seed(db_session, seed_user)
    conversation_id = await _new_conv(db_session, seed_user)

    events = await _drain(
        turn_svc.stream_turn(
            db_session,
            user_id=seed_user,
            conversation_id=conversation_id,
            message="what am I preparing for?",
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="Qualcomm."),
        )
    )

    kinds = [e["type"] for e in events]
    assert kinds[-1] == "done"
    assert kinds.count("done") == 1
    assert "delta" in kinds
    # Every delta precedes the terminal done.
    assert kinds.index("delta") < kinds.index("done")


async def test_streamed_turn_reports_the_routed_agent(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Agent attribution now comes from the orchestrator, not a second router."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _seed(db_session, seed_user)
    conversation_id = await _new_conv(db_session, seed_user)

    events = await _drain(
        turn_svc.stream_turn(
            db_session,
            user_id=seed_user,
            conversation_id=conversation_id,
            message="help me prepare my resume for this job application",
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="Here is resume advice."),
        )
    )
    done = events[-1]

    assert done["agent"] == "career"


async def test_manual_agent_override_is_honoured_when_streaming(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _seed(db_session, seed_user)
    conversation_id = await _new_conv(db_session, seed_user)

    events = await _drain(
        turn_svc.stream_turn(
            db_session,
            user_id=seed_user,
            conversation_id=conversation_id,
            message="anything at all",
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="ok"),
            agent_key="learning",
        )
    )

    assert events[-1]["agent"] == "learning"


async def test_streamed_turn_emits_safe_status_stages(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Status events carry a stage name and agent key — never reasoning."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _seed(db_session, seed_user)
    conversation_id = await _new_conv(db_session, seed_user)

    events = await _drain(
        turn_svc.stream_turn(
            db_session,
            user_id=seed_user,
            conversation_id=conversation_id,
            message="what am I preparing for?",
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="Qualcomm."),
        )
    )

    statuses = [e for e in events if e["type"] == "status"]
    assert statuses, "the client needs progress to display"
    assert {"understanding", "retrieving_context", "answering"} <= {
        s["stage"] for s in statuses
    }
    # A status event carries only these keys — no prompt, no reasoning, no text.
    for status in statuses:
        assert set(status) == {"type", "stage", "agent"}
    assert events[-1]["stages"]


async def test_streamed_and_nonstreamed_turns_agree(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same input, same pipeline: the two endpoints must not diverge.

    This is the guarantee the old architecture could not make, and the one that
    keeps a future turn-level change from landing on only one path.
    """
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _seed(db_session, seed_user)

    message = "what am I preparing for?"
    conv_run = await _new_conv(db_session, seed_user)
    run_result = await turn_svc.run_turn(
        db_session,
        user_id=seed_user,
        conversation_id=conv_run,
        message=message,
        embedding_service=_embeddings(),
        llm=FakeLLMProvider(reply="You are preparing for Qualcomm."),
    )

    conv_stream = await _new_conv(db_session, seed_user)
    events = await _drain(
        turn_svc.stream_turn(
            db_session,
            user_id=seed_user,
            conversation_id=conv_stream,
            message=message,
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="You are preparing for Qualcomm."),
        )
    )
    done = events[-1]
    streamed_text = "".join(e["text"] for e in events if e["type"] == "delta")

    assert streamed_text == run_result.reply
    assert done["memories_used"] == run_result.memories_used
    assert done["model"] == run_result.model


async def test_streamed_turn_persists_the_assistant_message(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _seed(db_session, seed_user)
    conversation_id = await _new_conv(db_session, seed_user)

    events = await _drain(
        turn_svc.stream_turn(
            db_session,
            user_id=seed_user,
            conversation_id=conversation_id,
            message="what am I preparing for?",
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="Qualcomm."),
        )
    )

    stored, _ = await msg_repo.list_messages(
        db_session,
        conversation_id=conversation_id,
        user_id=seed_user,
        limit=10,
        offset=0,
    )
    assistant = [m for m in stored if m.role is MessageRole.ASSISTANT]
    assert len(assistant) == 1
    assert assistant[0].content == "Qualcomm."
    assert str(assistant[0].id) == events[-1]["assistant_message_id"]
    # The routing explanation rides on the persisted message, so a refetched
    # conversation can still badge which agent answered.
    assert assistant[0].extra_metadata is not None
    assert "agent_key" in assistant[0].extra_metadata


async def test_orchestration_failure_still_yields_a_reply(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guaranteed fallback survives the unification.

    An orchestrator fault must cost latency, never the user's answer.
    """
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _seed(db_session, seed_user)
    conversation_id = await _new_conv(db_session, seed_user)

    async def _boom(*args: Any, **kwargs: Any) -> AsyncIterator[dict]:
        raise RuntimeError("orchestrator exploded")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(
        "app.services.agents.orchestrator_service.orchestrate_stream", _boom
    )

    events = await _drain(
        turn_svc.stream_turn(
            db_session,
            user_id=seed_user,
            conversation_id=conversation_id,
            message="what am I preparing for?",
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="Fallback reply."),
        )
    )

    done = events[-1]
    assert done["type"] == "done"
    text = "".join(e["text"] for e in events if e["type"] == "delta")
    assert text == "Fallback reply."
    # No orchestrated route to attribute when the fallback answered.
    assert done["agent"] is None


async def test_instant_recall_still_short_circuits_the_stream(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The no-model fast path must survive the rewrite."""
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await mem_repo.create_memory(
        db_session,
        user_id=seed_user,
        category=MemoryCategory.PROFILE,
        content="Name is Iqbal",
        importance_score=0.9,
        confidence_score=0.9,
    )
    await db_session.commit()
    conversation_id = await _new_conv(db_session, seed_user)

    events = await _drain(
        turn_svc.stream_turn(
            db_session,
            user_id=seed_user,
            conversation_id=conversation_id,
            message="what is my name?",
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="SHOULD NOT BE USED"),
        )
    )

    done = events[-1]
    assert done["model"] == "gummy-instant-recall"
    assert done["agent"] == "recall"
    assert "SHOULD NOT BE USED" not in "".join(
        e.get("text", "") for e in events if e["type"] == "delta"
    )
