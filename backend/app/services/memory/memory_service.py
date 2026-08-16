"""Memory service — business logic for the Memory CRUD layer.

Owns validation beyond schema shape, the memory lifecycle (create/update/archive/
soft-delete), version-history creation, and score defaults. It orchestrates the
repository and owns the transaction (commits its unit of work).

Versioning rules:
  * create  -> version 1 (reason: created)
  * update  -> new snapshot only when content changes (reason: edited)
  * archive -> new snapshot recording the lifecycle change (reason: archived)
  * delete  -> soft delete only; history is preserved, no new snapshot
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    DEFAULT_CONFIDENCE_SCORE,
    DEFAULT_IMPORTANCE_SCORE,
    INITIAL_VERSION_NUMBER,
)
from app.core.exceptions import AppError
from app.models.enums import MemoryCategory, MemoryChangeReason, MemoryStatus
from app.models.memory import Memory
from app.repositories import memory_repository as repo
from app.schemas.memory import MemoryCreate, MemoryUpdate
from app.services.memory import consolidation
from app.services.memory.consolidation import Resolution
from app.workers.embedding_worker import embedding_worker

logger = logging.getLogger(__name__)


class MemoryNotFoundError(AppError):
    """Raised when a memory does not exist (or is soft-deleted) for the tenant."""

    def __init__(self, memory_id: uuid.UUID) -> None:
        super().__init__(
            f"Memory {memory_id} not found.",
            code="memory_not_found",
            status_code=404,
        )


class EmptyUpdateError(AppError):
    """Raised when an update request carries no changeable fields."""

    def __init__(self) -> None:
        super().__init__(
            "No fields provided to update.",
            code="empty_update",
            status_code=400,
        )


async def _consolidate(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    category: MemoryCategory,
    content: str,
) -> Memory | None:
    """Fold an incoming fact into what is already known.

    Returns the strengthened existing memory when the fact is already stored (so
    the caller creates nothing), or ``None`` when it should be inserted — having
    first retired any memory this one replaces.

    Best-effort: a consolidation failure falls back to plain insertion, because
    losing a fact is worse than storing it twice.
    """
    try:
        decision = await consolidation.resolve(
            session, user_id=user_id, category=category, content=content
        )
    except Exception:
        logger.exception("memory consolidation failed; storing as new")
        return None

    if decision.resolution is Resolution.DUPLICATE and decision.existing:
        consolidation.reinforce(decision.existing)
        await session.commit()
        await session.refresh(decision.existing)
        logger.info(
            "memory reinforced instead of duplicated (similarity=%.2f)",
            decision.similarity,
        )
        return decision.existing

    if decision.resolution is Resolution.SUPERSEDES and decision.existing:
        consolidation.supersede(decision.existing)
        await repo.add_version(
            session,
            memory_id=decision.existing.id,
            version_number=await repo.next_version_number(
                session, decision.existing.id
            ),
            content_snapshot=decision.existing.content,
            change_reason=MemoryChangeReason.ARCHIVED,
        )
        await session.flush()
        logger.info(
            "memory superseded by a more specific fact (similarity=%.2f)",
            decision.similarity,
        )
    return None


async def create_memory(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    payload: MemoryCreate,
    consolidate: bool = True,
) -> Memory:
    """Create a memory (applying score defaults) and its first version.

    By default the incoming fact is first consolidated against what is already
    stored, so restating something Gummy knows strengthens that memory instead
    of appending a competing copy. Pass ``consolidate=False`` for an explicit
    user-authored memory that must be stored verbatim.
    """
    if consolidate:
        existing = await _consolidate(
            session,
            user_id=user_id,
            category=payload.category,
            content=payload.content,
        )
        if existing is not None:
            return existing

    importance = (
        payload.importance_score
        if payload.importance_score is not None
        else DEFAULT_IMPORTANCE_SCORE
    )
    confidence = (
        payload.confidence_score
        if payload.confidence_score is not None
        else DEFAULT_CONFIDENCE_SCORE
    )

    memory = await repo.create_memory(
        session,
        user_id=user_id,
        category=payload.category,
        content=payload.content,
        importance_score=importance,
        confidence_score=confidence,
    )
    await repo.add_version(
        session,
        memory_id=memory.id,
        version_number=INITIAL_VERSION_NUMBER,
        content_snapshot=memory.content,
        change_reason=MemoryChangeReason.CREATED,
    )
    await session.commit()
    await session.refresh(memory)
    # Keep the embedding fresh automatically (background, best-effort).
    embedding_worker.enqueue(memory.id, user_id)
    return memory


async def get_memory(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    memory_id: uuid.UUID,
) -> Memory:
    """Return a tenant-scoped, non-deleted memory or raise 404."""
    memory = await repo.get_memory(session, memory_id=memory_id, user_id=user_id)
    if memory is None:
        raise MemoryNotFoundError(memory_id)
    return memory


async def list_memories(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    category: MemoryCategory | None,
    status: MemoryStatus | None,
    limit: int,
    offset: int,
) -> tuple[list[Memory], int]:
    """Return a page of memories and the total match count."""
    return await repo.list_memories(
        session,
        user_id=user_id,
        category=category,
        status=status,
        limit=limit,
        offset=offset,
    )


async def update_memory(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    memory_id: uuid.UUID,
    payload: MemoryUpdate,
) -> Memory:
    """Update fields and snapshot a new version when content changes."""
    memory = await get_memory(session, user_id=user_id, memory_id=memory_id)

    # Only fields the client actually sent, dropping explicit nulls.
    changes = {
        key: value
        for key, value in payload.model_dump(exclude_unset=True).items()
        if value is not None
    }
    if not changes:
        raise EmptyUpdateError()

    content_changed = "content" in changes and changes["content"] != memory.content

    await repo.update_memory(
        session,
        memory,
        content=changes.get("content"),
        category=changes.get("category"),
        importance_score=changes.get("importance_score"),
        confidence_score=changes.get("confidence_score"),
    )

    if content_changed:
        version_number = await repo.next_version_number(session, memory.id)
        await repo.add_version(
            session,
            memory_id=memory.id,
            version_number=version_number,
            content_snapshot=memory.content,
            change_reason=MemoryChangeReason.EDITED,
        )

    await session.commit()
    await session.refresh(memory)
    # Re-embed on edit (the worker dedupes if content is unchanged).
    embedding_worker.enqueue(memory.id, user_id)
    return memory


async def archive_memory(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    memory_id: uuid.UUID,
) -> Memory:
    """Archive a memory, preserving history. Idempotent if already archived."""
    memory = await get_memory(session, user_id=user_id, memory_id=memory_id)
    if memory.status == MemoryStatus.ARCHIVED:
        return memory

    await repo.archive_memory(session, memory)
    version_number = await repo.next_version_number(session, memory.id)
    await repo.add_version(
        session,
        memory_id=memory.id,
        version_number=version_number,
        content_snapshot=memory.content,
        change_reason=MemoryChangeReason.ARCHIVED,
    )
    await session.commit()
    await session.refresh(memory)
    return memory


async def restore_memory(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    memory_id: uuid.UUID,
) -> Memory:
    """Un-archive a memory (back to active). Idempotent if already active."""
    memory = await get_memory(session, user_id=user_id, memory_id=memory_id)
    if memory.status == MemoryStatus.ACTIVE:
        return memory
    await repo.restore_memory(session, memory)
    await session.commit()
    await session.refresh(memory)
    return memory


async def delete_memory(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    memory_id: uuid.UUID,
) -> None:
    """Soft-delete a memory (history preserved). Raises 404 if not found."""
    memory = await get_memory(session, user_id=user_id, memory_id=memory_id)
    await repo.delete_memory(session, memory)
    await session.commit()
