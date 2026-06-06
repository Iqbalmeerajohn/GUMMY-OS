"""Data-access layer for memories and their version history.

Pure persistence: builds and runs queries, mutates ORM instances, and flushes —
but never commits (the service owns the unit of work) and makes no business
decisions (scoring, lifecycle rules live in the service).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory, MemoryChangeReason, MemoryStatus
from app.models.memory import Memory
from app.models.memory_version import MemoryVersion

# ── Memories ──────────────────────────────────────────────────────────────────


async def create_memory(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    category: MemoryCategory,
    content: str,
    importance_score: float,
    confidence_score: float,
) -> Memory:
    """Insert a new active memory and flush to populate its id."""
    memory = Memory(
        user_id=user_id,
        category=category,
        content=content,
        importance_score=importance_score,
        confidence_score=confidence_score,
        status=MemoryStatus.ACTIVE,
    )
    session.add(memory)
    await session.flush()
    return memory


async def get_memory(
    session: AsyncSession,
    *,
    memory_id: uuid.UUID,
    user_id: uuid.UUID,
    include_deleted: bool = False,
) -> Memory | None:
    """Fetch a single tenant-scoped memory, excluding soft-deleted by default."""
    stmt = select(Memory).where(
        Memory.id == memory_id,
        Memory.user_id == user_id,
    )
    if not include_deleted:
        stmt = stmt.where(Memory.deleted_at.is_(None))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_memories(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    category: MemoryCategory | None = None,
    status: MemoryStatus | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Memory], int]:
    """Return a page of tenant-scoped memories and the total match count."""
    filters = [Memory.user_id == user_id, Memory.deleted_at.is_(None)]
    if category is not None:
        filters.append(Memory.category == category)
    if status is not None:
        filters.append(Memory.status == status)

    total = await session.scalar(
        select(func.count()).select_from(Memory).where(*filters)
    )
    stmt = (
        select(Memory)
        .where(*filters)
        .order_by(Memory.created_at.desc(), Memory.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), int(total or 0)


async def update_memory(
    session: AsyncSession,
    memory: Memory,
    *,
    content: str | None = None,
    importance_score: float | None = None,
    confidence_score: float | None = None,
) -> Memory:
    """Apply field updates to a loaded memory and flush."""
    if content is not None:
        memory.content = content
    if importance_score is not None:
        memory.importance_score = importance_score
    if confidence_score is not None:
        memory.confidence_score = confidence_score
    await session.flush()
    return memory


async def archive_memory(session: AsyncSession, memory: Memory) -> Memory:
    """Mark a loaded memory as archived."""
    memory.status = MemoryStatus.ARCHIVED
    await session.flush()
    return memory


async def delete_memory(session: AsyncSession, memory: Memory) -> Memory:
    """Soft delete a loaded memory by stamping ``deleted_at``."""
    memory.deleted_at = datetime.now(UTC)
    await session.flush()
    return memory


# ── Version history ───────────────────────────────────────────────────────────


async def next_version_number(session: AsyncSession, memory_id: uuid.UUID) -> int:
    """Return the next sequential version number for a memory (1-based)."""
    current = await session.scalar(
        select(func.max(MemoryVersion.version_number)).where(
            MemoryVersion.memory_id == memory_id
        )
    )
    return int(current or 0) + 1


async def add_version(
    session: AsyncSession,
    *,
    memory_id: uuid.UUID,
    version_number: int,
    content_snapshot: str,
    change_reason: MemoryChangeReason,
) -> MemoryVersion:
    """Append an immutable version snapshot and flush."""
    version = MemoryVersion(
        memory_id=memory_id,
        version_number=version_number,
        content_snapshot=content_snapshot,
        change_reason=change_reason,
    )
    session.add(version)
    await session.flush()
    return version


async def list_versions(
    session: AsyncSession, *, memory_id: uuid.UUID
) -> list[MemoryVersion]:
    """Return all version snapshots for a memory, oldest first."""
    stmt = (
        select(MemoryVersion)
        .where(MemoryVersion.memory_id == memory_id)
        .order_by(MemoryVersion.version_number)
    )
    return list((await session.execute(stmt)).scalars().all())
