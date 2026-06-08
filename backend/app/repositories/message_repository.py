"""Data-access layer for messages (append-only; persistence only, no commit).

Messages are immutable turns. The repository appends and reads them; ordering and
recency-window selection live here, but token budgeting and turn orchestration are
the service's job (see PHASE2_PLAN.md §12).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MessageRole
from app.models.message import Message


async def next_seq(
    session: AsyncSession, conversation_id: uuid.UUID
) -> int:
    """Return the next monotonic ordinal for a conversation (1-based).

    Flushed-but-uncommitted rows are visible within the session, so successive
    appends in one transaction each see the prior seq. The
    ``(conversation_id, seq)`` unique constraint turns a concurrent collision
    into an error rather than silent reordering.
    """
    current = await session.scalar(
        select(func.max(Message.seq)).where(
            Message.conversation_id == conversation_id
        )
    )
    return int(current or 0) + 1


async def append_message(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    role: MessageRole,
    content: str,
    token_count: int | None = None,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    extra_metadata: dict | None = None,
) -> Message:
    """Insert a new message turn (next seq assigned) and flush to populate id."""
    message = Message(
        conversation_id=conversation_id,
        user_id=user_id,
        seq=await next_seq(session, conversation_id),
        role=role,
        content=content,
        token_count=token_count,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        extra_metadata=extra_metadata,
    )
    session.add(message)
    await session.flush()
    return message


async def list_messages(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    limit: int,
    offset: int,
) -> tuple[list[Message], int]:
    """Return a page of a conversation's messages (oldest first) and the total.

    Tenant-scoped on the denormalized ``user_id`` so the query is covered by the
    direct RLS policy and the conversation's ownership is enforced implicitly.
    """
    filters = [
        Message.conversation_id == conversation_id,
        Message.user_id == user_id,
    ]
    total = await session.scalar(
        select(func.count()).select_from(Message).where(*filters)
    )
    stmt = (
        select(Message)
        .where(*filters)
        .order_by(Message.seq.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), int(total or 0)


async def recent_messages(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    limit: int,
) -> list[Message]:
    """Return the most recent ``limit`` messages in chronological order.

    Fetches newest-first (so the cap keeps the latest turns) then reverses to
    chronological order for prompt assembly.
    """
    stmt = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.user_id == user_id,
        )
        .order_by(Message.seq.desc())
        .limit(limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    rows.reverse()
    return rows


async def get_message(
    session: AsyncSession,
    *,
    message_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Message | None:
    """Fetch a single tenant-scoped message by id, if it exists."""
    stmt = select(Message).where(
        Message.id == message_id,
        Message.user_id == user_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def messages_after(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    after_seq: int,
    limit: int,
) -> list[Message]:
    """Return messages with ``seq`` greater than ``after_seq`` (oldest first).

    The summarization delta: everything appended since a summary's watermark.
    ``after_seq=0`` returns the whole thread.
    """
    stmt = (
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.user_id == user_id,
            Message.seq > after_seq,
        )
        .order_by(Message.seq.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def count_messages(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> int:
    """Return the number of messages in a conversation (tenant-scoped)."""
    total = await session.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.user_id == user_id,
        )
    )
    return int(total or 0)
