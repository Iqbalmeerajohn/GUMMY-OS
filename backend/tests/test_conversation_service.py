"""Service-layer tests for conversation + message lifecycle (M3)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AgentContext, ConversationStatus, MessageRole
from app.repositories import message_repository as msg_repo
from app.schemas.conversation import ConversationCreate, ConversationUpdate
from app.services.conversation import conversation_service as svc
from app.services.conversation import message_service as msg_svc
from app.services.conversation.conversation_service import (
    ConversationNotFoundError,
    EmptyUpdateError,
)
from app.services.llm.fake_provider import FakeLLMProvider


async def test_create_applies_defaults(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv = await svc.create_conversation(
        db_session, user_id=seed_user, payload=ConversationCreate()
    )
    assert conv.status is ConversationStatus.ACTIVE
    assert conv.agent_context is AgentContext.GENERAL
    assert conv.pinned is False
    assert conv.message_count == 0
    assert conv.title is None


async def test_get_missing_raises_404(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    with pytest.raises(ConversationNotFoundError):
        await svc.get_conversation(
            db_session, user_id=seed_user, conversation_id=uuid.uuid4()
        )


async def test_get_is_tenant_scoped(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv = await svc.create_conversation(
        db_session, user_id=seed_user, payload=ConversationCreate()
    )
    with pytest.raises(ConversationNotFoundError):
        await svc.get_conversation(
            db_session, user_id=uuid.uuid4(), conversation_id=conv.id
        )


async def test_list_with_filters(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    await svc.create_conversation(
        db_session,
        user_id=seed_user,
        payload=ConversationCreate(agent_context=AgentContext.CAREER),
    )
    general = await svc.create_conversation(
        db_session, user_id=seed_user, payload=ConversationCreate()
    )
    items, total = await svc.list_conversations(
        db_session,
        user_id=seed_user,
        status=None,
        agent_context=AgentContext.GENERAL,
        pinned=None,
        limit=10,
        offset=0,
    )
    assert total == 1
    assert items[0].id == general.id


async def test_update_rename_pin_archive(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv = await svc.create_conversation(
        db_session, user_id=seed_user, payload=ConversationCreate()
    )
    updated = await svc.update_conversation(
        db_session,
        user_id=seed_user,
        conversation_id=conv.id,
        payload=ConversationUpdate(
            title="Renamed", pinned=True, status=ConversationStatus.ARCHIVED
        ),
    )
    assert updated.title == "Renamed"
    assert updated.pinned is True
    assert updated.status is ConversationStatus.ARCHIVED


async def test_update_empty_payload_raises(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv = await svc.create_conversation(
        db_session, user_id=seed_user, payload=ConversationCreate()
    )
    with pytest.raises(EmptyUpdateError):
        await svc.update_conversation(
            db_session,
            user_id=seed_user,
            conversation_id=conv.id,
            payload=ConversationUpdate(),
        )


async def test_soft_delete_then_404(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv = await svc.create_conversation(
        db_session, user_id=seed_user, payload=ConversationCreate()
    )
    await svc.delete_conversation(
        db_session, user_id=seed_user, conversation_id=conv.id
    )
    with pytest.raises(ConversationNotFoundError):
        await svc.get_conversation(
            db_session, user_id=seed_user, conversation_id=conv.id
        )


# ── message_service (history) ─────────────────────────────────────────────────


async def test_message_history_ownership_checked(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    # Unknown conversation -> 404 (not an empty page).
    with pytest.raises(ConversationNotFoundError):
        await msg_svc.list_messages(
            db_session,
            user_id=seed_user,
            conversation_id=uuid.uuid4(),
            limit=10,
            offset=0,
        )


async def test_message_history_returns_ordered_page(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv = await svc.create_conversation(
        db_session, user_id=seed_user, payload=ConversationCreate()
    )
    for i in range(3):
        await msg_repo.append_message(
            db_session,
            conversation_id=conv.id,
            user_id=seed_user,
            role=MessageRole.USER,
            content=f"m{i}",
        )
    await db_session.commit()

    items, total = await msg_svc.list_messages(
        db_session, user_id=seed_user, conversation_id=conv.id, limit=2, offset=0
    )
    assert total == 3
    assert [m.content for m in items] == ["m0", "m1"]  # oldest first by seq


# ── title backfill (M5) ───────────────────────────────────────────────────────


async def test_backfill_title_sets_title_from_first_message(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv = await svc.create_conversation(
        db_session, user_id=seed_user, payload=ConversationCreate()
    )
    await msg_repo.append_message(
        db_session,
        conversation_id=conv.id,
        user_id=seed_user,
        role=MessageRole.USER,
        content="Help me plan a Qualcomm interview",
    )
    await msg_repo.append_message(
        db_session,
        conversation_id=conv.id,
        user_id=seed_user,
        role=MessageRole.ASSISTANT,
        content="Sure!",
    )
    await db_session.commit()

    title = await svc.backfill_title(
        db_session,
        user_id=seed_user,
        conversation_id=conv.id,
        llm=FakeLLMProvider(reply="Qualcomm Interview Prep"),
    )
    assert title == "Qualcomm Interview Prep"
    refreshed = await svc.get_conversation(
        db_session, user_id=seed_user, conversation_id=conv.id
    )
    assert refreshed.title == "Qualcomm Interview Prep"


async def test_backfill_title_falls_back_when_llm_empty(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    # Issue 6: an empty/failed LLM title must not leave the thread "Untitled" —
    # it falls back to a clean snippet of the first user message.
    conv = await svc.create_conversation(
        db_session, user_id=seed_user, payload=ConversationCreate()
    )
    await msg_repo.append_message(
        db_session,
        conversation_id=conv.id,
        user_id=seed_user,
        role=MessageRole.USER,
        content="where do i live?",
    )
    await db_session.commit()

    title = await svc.backfill_title(
        db_session,
        user_id=seed_user,
        conversation_id=conv.id,
        llm=FakeLLMProvider(reply="   "),
    )
    assert title == "Where do i live"


async def test_backfill_title_is_idempotent(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv = await svc.create_conversation(
        db_session,
        user_id=seed_user,
        payload=ConversationCreate(title="Existing"),
    )
    await msg_repo.append_message(
        db_session,
        conversation_id=conv.id,
        user_id=seed_user,
        role=MessageRole.USER,
        content="hello",
    )
    await db_session.commit()

    title = await svc.backfill_title(
        db_session,
        user_id=seed_user,
        conversation_id=conv.id,
        llm=FakeLLMProvider(reply="New Title"),
    )
    assert title is None  # already titled → no-op
    refreshed = await svc.get_conversation(
        db_session, user_id=seed_user, conversation_id=conv.id
    )
    assert refreshed.title == "Existing"


async def test_backfill_title_no_messages_returns_none(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv = await svc.create_conversation(
        db_session, user_id=seed_user, payload=ConversationCreate()
    )
    await db_session.commit()
    title = await svc.backfill_title(
        db_session,
        user_id=seed_user,
        conversation_id=conv.id,
        llm=FakeLLMProvider(reply="X"),
    )
    assert title is None
