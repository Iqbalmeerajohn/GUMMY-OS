"""Data-access layer for conversations (persistence only, no commit).

Pure persistence: builds and runs queries, mutates ORM instances, and flushes —
never commits (the service owns the unit of work) and makes no business decisions
(titles, summaries, counters policy live in the service). See PHASE2_PLAN.md §12.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.enums import AgentContext, ConversationStatus


async def create_conversation(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    title: str | None = None,
    agent_context: AgentContext = AgentContext.GENERAL,
) -> Conversation:
    """Insert a new active conversation and flush to populate its id."""
    conversation = Conversation(
        user_id=user_id,
        title=title,
        agent_context=agent_context,
        status=ConversationStatus.ACTIVE,
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def get_conversation(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    include_deleted: bool = False,
) -> Conversation | None:
    """Fetch a single tenant-scoped conversation, excluding soft-deleted."""
    stmt = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    )
    if not include_deleted:
        stmt = stmt.where(Conversation.deleted_at.is_(None))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_conversations(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    status: ConversationStatus | None = None,
    agent_context: AgentContext | None = None,
    pinned: bool | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Conversation], int]:
    """Return a page of tenant-scoped conversations and the total match count.

    Ordered for the recency UI: pinned first, then most-recent activity
    (``last_message_at``, falling back to ``created_at``).
    """
    filters = [
        Conversation.user_id == user_id,
        Conversation.deleted_at.is_(None),
    ]
    if status is not None:
        filters.append(Conversation.status == status)
    if agent_context is not None:
        filters.append(Conversation.agent_context == agent_context)
    if pinned is not None:
        filters.append(Conversation.pinned.is_(pinned))

    total = await session.scalar(
        select(func.count()).select_from(Conversation).where(*filters)
    )
    sort_key = func.coalesce(
        Conversation.last_message_at, Conversation.created_at
    )
    stmt = (
        select(Conversation)
        .where(*filters)
        .order_by(
            Conversation.pinned.desc(),
            sort_key.desc(),
            Conversation.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), int(total or 0)


async def update_conversation(
    session: AsyncSession,
    conversation: Conversation,
    *,
    title: str | None = None,
    pinned: bool | None = None,
    status: ConversationStatus | None = None,
    agent_context: AgentContext | None = None,
) -> Conversation:
    """Apply field updates to a loaded conversation and flush.

    Only non-None arguments are applied (so ``title`` cannot be cleared here;
    that is intentional — titles are set/regenerated, not blanked).
    """
    if title is not None:
        conversation.title = title
    if pinned is not None:
        conversation.pinned = pinned
    if status is not None:
        conversation.status = status
    if agent_context is not None:
        conversation.agent_context = agent_context
    await session.flush()
    return conversation


async def touch_last_message(
    session: AsyncSession,
    conversation: Conversation,
    *,
    last_message_at: datetime,
    message_count: int,
) -> Conversation:
    """Record new activity (recency + denormalized counter) and flush."""
    conversation.last_message_at = last_message_at
    conversation.message_count = message_count
    await session.flush()
    return conversation


async def soft_delete_conversation(
    session: AsyncSession,
    conversation: Conversation,
    *,
    deleted_at: datetime,
) -> Conversation:
    """Soft delete a loaded conversation by stamping ``deleted_at``."""
    conversation.deleted_at = deleted_at
    await session.flush()
    return conversation
