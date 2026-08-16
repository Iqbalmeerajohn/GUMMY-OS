"""Repository-layer tests for the Phase 2 Conversation System (direct DB).

Runs against in-memory SQLite (the shared fixtures). Exercises persistence,
tenant scoping, ordering, pagination, and the version/recency helpers. RLS
enforcement itself is proven separately in test_rls_postgres.py (Postgres only).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    AgentContext,
    ConversationStatus,
    MemoryCategory,
    MessageRole,
    SourceKind,
    SummaryType,
)
from app.repositories import conversation_repository as conv_repo
from app.repositories import conversation_summary_embedding_repository as emb_repo
from app.repositories import conversation_summary_repository as sum_repo
from app.repositories import memory_repository as mem_repo
from app.repositories import memory_source_repository as src_repo
from app.repositories import message_repository as msg_repo

_VECTOR = [0.1] * 384


# ── conversations ─────────────────────────────────────────────────────────────


async def test_create_and_get_conversation(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv = await conv_repo.create_conversation(
        db_session, user_id=seed_user, title="Hello"
    )
    await db_session.commit()
    fetched = await conv_repo.get_conversation(
        db_session, conversation_id=conv.id, user_id=seed_user
    )
    assert fetched is not None
    assert fetched.title == "Hello"
    assert fetched.status is ConversationStatus.ACTIVE
    assert fetched.agent_context is AgentContext.GENERAL
    assert fetched.pinned is False
    assert fetched.message_count == 0


async def test_get_conversation_is_tenant_scoped(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv = await conv_repo.create_conversation(db_session, user_id=seed_user)
    await db_session.commit()
    assert (
        await conv_repo.get_conversation(
            db_session, conversation_id=conv.id, user_id=uuid.uuid4()
        )
        is None
    )


async def test_list_conversations_pagination_and_total(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    for _ in range(3):
        await conv_repo.create_conversation(db_session, user_id=seed_user)
    await db_session.commit()
    items, total = await conv_repo.list_conversations(
        db_session, user_id=seed_user, limit=2, offset=0
    )
    assert total == 3
    assert len(items) == 2


async def test_list_conversations_orders_pinned_then_recency(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    now = datetime.now(UTC)
    old = await conv_repo.create_conversation(db_session, user_id=seed_user)
    recent = await conv_repo.create_conversation(db_session, user_id=seed_user)
    pinned = await conv_repo.create_conversation(db_session, user_id=seed_user)
    await conv_repo.touch_last_message(
        db_session, old, last_message_at=now - timedelta(days=2), message_count=1
    )
    await conv_repo.touch_last_message(
        db_session, recent, last_message_at=now, message_count=1
    )
    await conv_repo.touch_last_message(
        db_session, pinned, last_message_at=now - timedelta(days=5), message_count=1
    )
    await conv_repo.update_conversation(db_session, pinned, pinned=True)
    await db_session.commit()

    items, _ = await conv_repo.list_conversations(
        db_session, user_id=seed_user, limit=10, offset=0
    )
    # Pinned first (despite oldest activity), then most-recent activity.
    assert [c.id for c in items] == [pinned.id, recent.id, old.id]


async def test_list_conversations_filters(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    a = await conv_repo.create_conversation(
        db_session, user_id=seed_user, agent_context=AgentContext.CAREER
    )
    await conv_repo.create_conversation(
        db_session, user_id=seed_user, agent_context=AgentContext.GENERAL
    )
    await conv_repo.update_conversation(
        db_session, a, status=ConversationStatus.ARCHIVED
    )
    await db_session.commit()

    archived, total = await conv_repo.list_conversations(
        db_session,
        user_id=seed_user,
        status=ConversationStatus.ARCHIVED,
        limit=10,
        offset=0,
    )
    assert total == 1
    assert archived[0].id == a.id

    career, _ = await conv_repo.list_conversations(
        db_session,
        user_id=seed_user,
        agent_context=AgentContext.CAREER,
        limit=10,
        offset=0,
    )
    assert [c.id for c in career] == [a.id]


async def test_soft_delete_excludes_conversation(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv = await conv_repo.create_conversation(db_session, user_id=seed_user)
    await conv_repo.soft_delete_conversation(
        db_session, conv, deleted_at=datetime.now(UTC)
    )
    await db_session.commit()
    assert (
        await conv_repo.get_conversation(
            db_session, conversation_id=conv.id, user_id=seed_user
        )
        is None
    )
    assert (
        await conv_repo.get_conversation(
            db_session,
            conversation_id=conv.id,
            user_id=seed_user,
            include_deleted=True,
        )
        is not None
    )
    _, total = await conv_repo.list_conversations(
        db_session, user_id=seed_user, limit=10, offset=0
    )
    assert total == 0


# ── messages ──────────────────────────────────────────────────────────────────


async def _new_conv(db_session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    conv = await conv_repo.create_conversation(db_session, user_id=user_id)
    await db_session.flush()
    return conv.id


async def test_append_and_list_messages(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _new_conv(db_session, seed_user)
    for i in range(3):
        await msg_repo.append_message(
            db_session,
            conversation_id=conv_id,
            user_id=seed_user,
            role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
            content=f"m{i}",
        )
    await db_session.commit()

    items, total = await msg_repo.list_messages(
        db_session, conversation_id=conv_id, user_id=seed_user, limit=2, offset=0
    )
    assert total == 3
    assert [m.content for m in items] == ["m0", "m1"]  # oldest first


async def test_append_message_persists_metadata_and_cost(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _new_conv(db_session, seed_user)
    msg = await msg_repo.append_message(
        db_session,
        conversation_id=conv_id,
        user_id=seed_user,
        role=MessageRole.ASSISTANT,
        content="hi",
        model="claude-x",
        input_tokens=10,
        output_tokens=5,
        extra_metadata={"citations": [1, 2]},
    )
    await db_session.commit()
    assert msg.model == "claude-x"
    assert msg.input_tokens == 10
    assert msg.extra_metadata == {"citations": [1, 2]}


async def test_recent_messages_caps_and_orders(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _new_conv(db_session, seed_user)
    for i in range(5):
        await msg_repo.append_message(
            db_session,
            conversation_id=conv_id,
            user_id=seed_user,
            role=MessageRole.USER,
            content=f"m{i}",
        )
    await db_session.commit()
    recent = await msg_repo.recent_messages(
        db_session, conversation_id=conv_id, user_id=seed_user, limit=2
    )
    # Last two, in chronological order.
    assert [m.content for m in recent] == ["m3", "m4"]
    assert (
        await msg_repo.count_messages(
            db_session, conversation_id=conv_id, user_id=seed_user
        )
        == 5
    )


async def test_messages_are_tenant_scoped(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _new_conv(db_session, seed_user)
    await msg_repo.append_message(
        db_session,
        conversation_id=conv_id,
        user_id=seed_user,
        role=MessageRole.USER,
        content="secret",
    )
    await db_session.commit()
    _, total = await msg_repo.list_messages(
        db_session,
        conversation_id=conv_id,
        user_id=uuid.uuid4(),
        limit=10,
        offset=0,
    )
    assert total == 0


# ── summaries ─────────────────────────────────────────────────────────────────


async def test_summary_version_increments(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _new_conv(db_session, seed_user)
    assert await sum_repo.next_version_number(db_session, conv_id) == 1
    await sum_repo.add_summary(
        db_session,
        conversation_id=conv_id,
        user_id=seed_user,
        summary_type=SummaryType.ROLLING,
        content="v1",
        version_number=1,
    )
    await db_session.flush()
    assert await sum_repo.next_version_number(db_session, conv_id) == 2


async def test_latest_summary_by_type(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _new_conv(db_session, seed_user)
    await sum_repo.add_summary(
        db_session,
        conversation_id=conv_id,
        user_id=seed_user,
        summary_type=SummaryType.ROLLING,
        content="r1",
        version_number=1,
    )
    await sum_repo.add_summary(
        db_session,
        conversation_id=conv_id,
        user_id=seed_user,
        summary_type=SummaryType.ROLLING,
        content="r2",
        version_number=2,
    )
    await sum_repo.add_summary(
        db_session,
        conversation_id=conv_id,
        user_id=seed_user,
        summary_type=SummaryType.CLOSING,
        content="closing",
        version_number=3,
    )
    await db_session.commit()

    latest_any = await sum_repo.latest_summary(
        db_session, conversation_id=conv_id, user_id=seed_user
    )
    assert latest_any is not None and latest_any.content == "closing"

    latest_rolling = await sum_repo.latest_summary(
        db_session,
        conversation_id=conv_id,
        user_id=seed_user,
        summary_type=SummaryType.ROLLING,
    )
    assert latest_rolling is not None and latest_rolling.content == "r2"

    all_versions = await sum_repo.list_summaries(
        db_session, conversation_id=conv_id, user_id=seed_user
    )
    assert [s.version_number for s in all_versions] == [1, 2, 3]


# ── summary embeddings ────────────────────────────────────────────────────────


async def test_summary_embedding_crud(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _new_conv(db_session, seed_user)
    summary = await sum_repo.add_summary(
        db_session,
        conversation_id=conv_id,
        user_id=seed_user,
        summary_type=SummaryType.ROLLING,
        content="s",
        version_number=1,
    )
    await db_session.flush()
    created = await emb_repo.create_embedding(
        db_session,
        user_id=seed_user,
        summary_id=summary.id,
        embedding_model="test-model",
        embedding_dimension=384,
        content_hash="h1",
        embedding_vector=_VECTOR,
    )
    await db_session.commit()

    fetched = await emb_repo.get_embedding(
        db_session, summary_id=summary.id, embedding_model="test-model"
    )
    assert fetched is not None and fetched.id == created.id

    await emb_repo.update_embedding(
        db_session,
        fetched,
        embedding_vector=_VECTOR,
        content_hash="h2",
        embedding_dimension=384,
    )
    await db_session.commit()
    assert fetched.content_hash == "h2"

    listed = await emb_repo.list_embeddings(db_session, summary_id=summary.id)
    assert len(listed) == 1


# ── memory sources (provenance) ───────────────────────────────────────────────


async def test_memory_source_link_and_lookup(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _new_conv(db_session, seed_user)
    msg = await msg_repo.append_message(
        db_session,
        conversation_id=conv_id,
        user_id=seed_user,
        role=MessageRole.USER,
        content="I target Qualcomm",
    )
    memory = await mem_repo.create_memory(
        db_session,
        user_id=seed_user,
        category=MemoryCategory.CAREER,
        content="Targeting Qualcomm",
        importance_score=0.8,
        confidence_score=0.9,
    )
    await db_session.flush()
    await src_repo.link_source(
        db_session,
        user_id=seed_user,
        memory_id=memory.id,
        conversation_id=conv_id,
        message_id=msg.id,
        source_kind=SourceKind.CONVERSATION,
    )
    await db_session.commit()

    by_memory = await src_repo.list_for_memory(
        db_session, memory_id=memory.id, user_id=seed_user
    )
    assert len(by_memory) == 1
    assert by_memory[0].conversation_id == conv_id
    assert by_memory[0].message_id == msg.id

    by_conv = await src_repo.list_for_conversation(
        db_session, conversation_id=conv_id, user_id=seed_user
    )
    assert [s.memory_id for s in by_conv] == [memory.id]


async def test_memory_source_is_tenant_scoped(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    conv_id = await _new_conv(db_session, seed_user)
    memory = await mem_repo.create_memory(
        db_session,
        user_id=seed_user,
        category=MemoryCategory.PROFILE,
        content="x",
        importance_score=0.5,
        confidence_score=0.5,
    )
    await db_session.flush()
    await src_repo.link_source(
        db_session,
        user_id=seed_user,
        memory_id=memory.id,
        conversation_id=conv_id,
    )
    await db_session.commit()
    assert (
        await src_repo.list_for_conversation(
            db_session, conversation_id=conv_id, user_id=uuid.uuid4()
        )
        == []
    )
