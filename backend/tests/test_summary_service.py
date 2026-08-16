"""Rolling-summary service tests (M5): trigger policy, versioning, embedding."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import EMBEDDING_DIMENSION
from app.models.enums import MessageRole, SummaryType
from app.repositories import conversation_summary_embedding_repository as emb_repo
from app.repositories import conversation_summary_repository as sum_repo
from app.repositories import message_repository as msg_repo
from app.schemas.conversation import ConversationCreate
from app.services.conversation import conversation_service, summary_service
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.llm.fake_provider import FakeLLMProvider


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


async def _conv_with_messages(
    db_session: AsyncSession, user_id: uuid.UUID, count: int, content: str = "hi"
) -> uuid.UUID:
    conv = await conversation_service.create_conversation(
        db_session, user_id=user_id, payload=ConversationCreate()
    )
    for i in range(count):
        await msg_repo.append_message(
            db_session,
            conversation_id=conv.id,
            user_id=user_id,
            role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
            content=content,
        )
    await db_session.commit()
    return conv.id


async def test_below_threshold_no_summary(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _conv_with_messages(db_session, seed_user, count=1)
    result = await summary_service.maybe_refresh_rolling_summary(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        llm=FakeLLMProvider(reply="SUMMARY"),
        embedding_service=_embeddings(),
    )
    assert result is None
    latest = await sum_repo.latest_summary(
        db_session, conversation_id=conv_id, user_id=seed_user
    )
    assert latest is None


async def test_message_count_cap_triggers_refresh(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _conv_with_messages(db_session, seed_user, count=6)
    summary = await summary_service.maybe_refresh_rolling_summary(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        llm=FakeLLMProvider(reply="SUMMARY"),
        embedding_service=_embeddings(),
    )
    assert summary is not None
    assert summary.summary_type is SummaryType.ROLLING
    assert summary.version_number == 1
    assert summary.content == "SUMMARY"
    assert summary.covers_through_message_id is not None
    await db_session.commit()

    # Its embedding was generated.
    embeddings = await emb_repo.list_embeddings(db_session, summary_id=summary.id)
    assert len(embeddings) == 1
    assert embeddings[0].embedding_dimension == EMBEDDING_DIMENSION


async def test_token_pressure_triggers_refresh(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    # Two long messages exceed a low token threshold despite being under the count.
    conv_id = await _conv_with_messages(
        db_session, seed_user, count=2, content="word " * 50
    )
    summary = await summary_service.maybe_refresh_rolling_summary(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        llm=FakeLLMProvider(reply="SUMMARY"),
        embedding_service=_embeddings(),
        trigger_token_threshold=10,
        trigger_message_count=999,
    )
    assert summary is not None


async def test_second_refresh_summarizes_delta_only(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _conv_with_messages(db_session, seed_user, count=6)
    first = await summary_service.maybe_refresh_rolling_summary(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        llm=FakeLLMProvider(reply="S1"),
        embedding_service=_embeddings(),
    )
    assert first is not None
    await db_session.commit()

    # Append more messages, then refresh again.
    for _ in range(6):
        await msg_repo.append_message(
            db_session,
            conversation_id=conv_id,
            user_id=seed_user,
            role=MessageRole.USER,
            content="more",
        )
    await db_session.commit()

    llm = FakeLLMProvider(reply="S2")
    second = await summary_service.maybe_refresh_rolling_summary(
        db_session,
        user_id=seed_user,
        conversation_id=conv_id,
        llm=llm,
        embedding_service=_embeddings(),
    )
    assert second is not None
    assert second.version_number == 2
    # The prompt fed the previous summary + only the new (delta) messages.
    prompt = str(llm.calls[0]["messages"])
    assert "S1" in prompt  # previous summary carried forward
    assert second.covers_through_message_id != first.covers_through_message_id


async def test_summary_is_tenant_scoped(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _conv_with_messages(db_session, seed_user, count=6)
    # A different tenant sees no delta (messages are tenant-scoped) → no summary.
    result = await summary_service.maybe_refresh_rolling_summary(
        db_session,
        user_id=uuid.uuid4(),
        conversation_id=conv_id,
        llm=FakeLLMProvider(reply="SUMMARY"),
        embedding_service=_embeddings(),
    )
    assert result is None
