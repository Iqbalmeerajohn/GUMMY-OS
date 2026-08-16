"""Data-access layer for conversation summaries (append-only; no commit).

Summaries are versioned, immutable rows (mirrors ``memory_versions``). The
repository appends versions and reads the latest; the summarization policy
(thresholds, what to summarize) is the service's job (see PHASE2_PLAN.md §5/§12).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_summary import ConversationSummary
from app.models.enums import SummaryType


async def next_version_number(session: AsyncSession, conversation_id: uuid.UUID) -> int:
    """Return the next sequential summary version for a conversation (1-based)."""
    current = await session.scalar(
        select(func.max(ConversationSummary.version_number)).where(
            ConversationSummary.conversation_id == conversation_id
        )
    )
    return int(current or 0) + 1


async def add_summary(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    summary_type: SummaryType,
    content: str,
    version_number: int,
    covers_through_message_id: uuid.UUID | None = None,
    model: str | None = None,
) -> ConversationSummary:
    """Append an immutable summary version and flush."""
    summary = ConversationSummary(
        conversation_id=conversation_id,
        user_id=user_id,
        summary_type=summary_type,
        content=content,
        version_number=version_number,
        covers_through_message_id=covers_through_message_id,
        model=model,
    )
    session.add(summary)
    await session.flush()
    return summary


async def latest_summary(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    summary_type: SummaryType | None = None,
) -> ConversationSummary | None:
    """Return the highest-version summary for a conversation, if any.

    Optionally filtered by ``summary_type`` (e.g. the latest *rolling* summary
    for per-turn context assembly).
    """
    filters = [
        ConversationSummary.conversation_id == conversation_id,
        ConversationSummary.user_id == user_id,
    ]
    if summary_type is not None:
        filters.append(ConversationSummary.summary_type == summary_type)
    stmt = (
        select(ConversationSummary)
        .where(*filters)
        .order_by(ConversationSummary.version_number.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_summaries(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[ConversationSummary]:
    """Return all summary versions for a conversation, oldest first."""
    stmt = (
        select(ConversationSummary)
        .where(
            ConversationSummary.conversation_id == conversation_id,
            ConversationSummary.user_id == user_id,
        )
        .order_by(ConversationSummary.version_number.asc())
    )
    return list((await session.execute(stmt)).scalars().all())
