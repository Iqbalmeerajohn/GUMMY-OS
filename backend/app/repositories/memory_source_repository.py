"""Data-access layer for memory provenance links (append-only; no commit).

Records where a memory was distilled from (a conversation/message). Persistence
only — the extraction policy that decides *what* becomes a memory lives in the
service and routes through the existing Memory Engine (see PHASE2_PLAN.md §7/§12).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SourceKind
from app.models.memory_source import MemorySource


async def link_source(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    memory_id: uuid.UUID,
    source_kind: SourceKind = SourceKind.CONVERSATION,
    conversation_id: uuid.UUID | None = None,
    message_id: uuid.UUID | None = None,
) -> MemorySource:
    """Insert a provenance link from a memory to its source and flush."""
    source = MemorySource(
        user_id=user_id,
        memory_id=memory_id,
        source_kind=source_kind,
        conversation_id=conversation_id,
        message_id=message_id,
    )
    session.add(source)
    await session.flush()
    return source


async def list_for_memory(
    session: AsyncSession,
    *,
    memory_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[MemorySource]:
    """Return all provenance links for a memory (tenant-scoped), oldest first."""
    stmt = (
        select(MemorySource)
        .where(
            MemorySource.memory_id == memory_id,
            MemorySource.user_id == user_id,
        )
        .order_by(MemorySource.created_at.asc(), MemorySource.id.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_for_conversation(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[MemorySource]:
    """Return all memories sourced from a conversation (tenant-scoped)."""
    stmt = (
        select(MemorySource)
        .where(
            MemorySource.conversation_id == conversation_id,
            MemorySource.user_id == user_id,
        )
        .order_by(MemorySource.created_at.asc(), MemorySource.id.asc())
    )
    return list((await session.execute(stmt)).scalars().all())
