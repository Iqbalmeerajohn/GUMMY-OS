"""Turn-service tests (M4): persistence, lifecycle, history, enrichment seam.

SQLite; pgvector search is monkeypatched (as in the chat tests).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory, MessageRole
from app.models.memory import Memory
from app.repositories import memory_repository as mem_repo
from app.repositories import message_repository as msg_repo
from app.schemas.conversation import ConversationCreate
from app.services.conversation import conversation_service, enrichment
from app.services.conversation import conversation_turn_service as turn_svc
from app.services.conversation.conversation_service import (
    ConversationNotFoundError,
)
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.llm.fake_provider import FakeLLMProvider
from app.workers.enrichment_worker import enrichment_worker


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


def _aware(dt: datetime) -> datetime:
    """Coerce to UTC-aware. SQLite returns naive datetimes for timezone=True
    columns (Postgres returns aware); normalize so cross-source comparisons work.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def _new_conv(db_session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    conv = await conversation_service.create_conversation(
        db_session, user_id=user_id, payload=ConversationCreate()
    )
    return conv.id


async def test_run_turn_persists_user_and_assistant_messages(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    conv_id = await _new_conv(db_session, seed_user)
    llm = FakeLLMProvider(reply="hi there")

    result = await turn_svc.run_turn(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        message="hello",
        embedding_service=_embeddings(),
        llm=llm,
    )

    items, total = await msg_repo.list_messages(
        db_session, conversation_id=conv_id, user_id=seed_user, limit=10, offset=0
    )
    assert total == 2
    assert items[0].role is MessageRole.USER
    assert items[0].content == "hello"
    assert items[1].role is MessageRole.ASSISTANT
    assert items[1].content == "hi there"
    assert items[1].model == "fake-model"
    assert items[1].output_tokens is not None
    # TurnResult points at the persisted rows.
    assert result.reply == "hi there"
    assert result.message_count == 2
    assert result.user_message_id == items[0].id
    assert result.assistant_message_id == items[1].id


async def test_run_turn_updates_conversation_lifecycle(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    conv_id = await _new_conv(db_session, seed_user)
    llm = FakeLLMProvider(reply="ok")

    await turn_svc.run_turn(
        db_session, user_id=seed_user, conversation_id=conv_id,
        message="first", embedding_service=_embeddings(), llm=llm,
    )
    conv = await conversation_service.get_conversation(
        db_session, user_id=seed_user, conversation_id=conv_id
    )
    assert conv.message_count == 2
    assert conv.last_message_at is not None
    first_activity = conv.last_message_at

    await turn_svc.run_turn(
        db_session, user_id=seed_user, conversation_id=conv_id,
        message="second", embedding_service=_embeddings(), llm=llm,
    )
    conv = await conversation_service.get_conversation(
        db_session, user_id=seed_user, conversation_id=conv_id
    )
    assert conv.message_count == 4
    assert conv.last_message_at is not None
    assert _aware(conv.last_message_at) >= _aware(first_activity)


async def test_run_turn_replays_history_into_prompt(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    conv_id = await _new_conv(db_session, seed_user)
    llm = FakeLLMProvider(reply="ok")

    await turn_svc.run_turn(
        db_session, user_id=seed_user, conversation_id=conv_id,
        message="first", embedding_service=_embeddings(), llm=llm,
    )
    await turn_svc.run_turn(
        db_session, user_id=seed_user, conversation_id=conv_id,
        message="second", embedding_service=_embeddings(), llm=llm,
    )

    # The second turn's prompt replays the prior user+assistant turns as history.
    assert llm.calls[-1]["messages"] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "second"},
    ]


async def test_run_turn_grounds_in_memory(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await mem_repo.create_memory(
        db_session, user_id=seed_user, category=MemoryCategory.CAREER,
        content="Targeting Qualcomm", importance_score=0.5, confidence_score=0.5,
    )
    await db_session.commit()
    conv_id = await _new_conv(db_session, seed_user)
    llm = FakeLLMProvider(reply="noted")

    result = await turn_svc.run_turn(
        db_session, user_id=seed_user, conversation_id=conv_id,
        message="what am I targeting?", embedding_service=_embeddings(), llm=llm,
    )
    assert result.memories_used == 1
    assert "Targeting Qualcomm" in str(llm.calls[0]["system"])


async def test_run_turn_injects_rolling_summary_into_prompt(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.enums import SummaryType
    from app.repositories import conversation_summary_repository as sum_repo

    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    conv_id = await _new_conv(db_session, seed_user)
    await sum_repo.add_summary(
        db_session,
        conversation_id=conv_id,
        user_id=seed_user,
        summary_type=SummaryType.ROLLING,
        content="PRIOR CONTEXT about the user",
        version_number=1,
    )
    await db_session.commit()

    llm = FakeLLMProvider(reply="ok")
    await turn_svc.run_turn(
        db_session, user_id=seed_user, conversation_id=conv_id,
        message="continue", embedding_service=_embeddings(), llm=llm,
    )
    system = str(llm.calls[-1]["system"])
    assert "<conversation_summary>" in system
    assert "PRIOR CONTEXT about the user" in system


async def test_run_turn_unknown_conversation_raises_404(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    with pytest.raises(ConversationNotFoundError):
        await turn_svc.run_turn(
            db_session,
            user_id=seed_user,
            conversation_id=uuid.uuid4(),
            message="hi",
            embedding_service=_embeddings(),
            llm=FakeLLMProvider(reply="x"),
        )


async def test_run_turn_enqueues_enrichment_after_commit(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    recorded: list[tuple[uuid.UUID, uuid.UUID]] = []

    def _spy(conversation_id: uuid.UUID, user_id: uuid.UUID) -> None:
        recorded.append((conversation_id, user_id))

    monkeypatch.setattr(enrichment_worker, "enqueue", _spy)
    conv_id = await _new_conv(db_session, seed_user)

    await turn_svc.run_turn(
        db_session, user_id=seed_user, conversation_id=conv_id,
        message="hi", embedding_service=_embeddings(), llm=FakeLLMProvider(reply="y"),
    )
    assert recorded == [(conv_id, seed_user)]


async def test_extraction_consumer_is_still_a_noop(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    # M6 will implement this; in M5 it must remain a no-op writing nothing.
    job = enrichment.EnrichmentJob(
        conversation_id=uuid.uuid4(), user_id=seed_user
    )
    result = await enrichment.extract_memories(
        db_session, job, FakeLLMProvider(reply="x"), _embeddings()
    )
    assert result is None
