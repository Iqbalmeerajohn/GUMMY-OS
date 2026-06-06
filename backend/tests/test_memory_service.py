"""Service-layer tests: lifecycle, versioning, defaults, validation."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory, MemoryChangeReason, MemoryStatus
from app.repositories import memory_repository as repo
from app.schemas.memory import MemoryCreate, MemoryUpdate
from app.services.memory import memory_service
from app.services.memory.memory_service import (
    EmptyUpdateError,
    MemoryNotFoundError,
)


async def _create(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    content: str = "I am preparing for Qualcomm",
    importance: float | None = None,
    confidence: float | None = None,
) -> uuid.UUID:
    memory = await memory_service.create_memory(
        session,
        user_id=user_id,
        payload=MemoryCreate(
            category=MemoryCategory.CAREER,
            content=content,
            importance_score=importance,
            confidence_score=confidence,
        ),
    )
    return memory.id


async def test_create_applies_score_defaults(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory_id = await _create(db_session, seed_user)
    memory = await memory_service.get_memory(
        db_session, user_id=seed_user, memory_id=memory_id
    )
    assert memory.importance_score == 0.5
    assert memory.confidence_score == 0.5


async def test_create_writes_version_one(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory_id = await _create(db_session, seed_user)
    versions = await repo.list_versions(db_session, memory_id=memory_id)
    assert len(versions) == 1
    assert versions[0].version_number == 1
    assert versions[0].change_reason is MemoryChangeReason.CREATED


async def test_update_content_creates_new_version(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory_id = await _create(db_session, seed_user)
    await memory_service.update_memory(
        db_session,
        user_id=seed_user,
        memory_id=memory_id,
        payload=MemoryUpdate(content="Now targeting NVIDIA"),
    )
    versions = await repo.list_versions(db_session, memory_id=memory_id)
    assert [v.version_number for v in versions] == [1, 2]
    assert versions[1].change_reason is MemoryChangeReason.EDITED
    assert versions[1].content_snapshot == "Now targeting NVIDIA"


async def test_update_scores_only_does_not_version(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory_id = await _create(db_session, seed_user)
    await memory_service.update_memory(
        db_session,
        user_id=seed_user,
        memory_id=memory_id,
        payload=MemoryUpdate(importance_score=0.9),
    )
    versions = await repo.list_versions(db_session, memory_id=memory_id)
    assert len(versions) == 1  # no content change -> no new snapshot


async def test_empty_update_raises(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory_id = await _create(db_session, seed_user)
    with pytest.raises(EmptyUpdateError):
        await memory_service.update_memory(
            db_session,
            user_id=seed_user,
            memory_id=memory_id,
            payload=MemoryUpdate(),
        )


async def test_archive_preserves_history_and_is_idempotent(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory_id = await _create(db_session, seed_user)
    archived = await memory_service.archive_memory(
        db_session, user_id=seed_user, memory_id=memory_id
    )
    assert archived.status is MemoryStatus.ARCHIVED

    versions = await repo.list_versions(db_session, memory_id=memory_id)
    assert [v.change_reason for v in versions] == [
        MemoryChangeReason.CREATED,
        MemoryChangeReason.ARCHIVED,
    ]

    # Archiving again is a no-op (no duplicate snapshot).
    await memory_service.archive_memory(
        db_session, user_id=seed_user, memory_id=memory_id
    )
    versions_after = await repo.list_versions(db_session, memory_id=memory_id)
    assert len(versions_after) == 2


async def test_delete_is_soft_and_then_not_found(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory_id = await _create(db_session, seed_user)
    await memory_service.delete_memory(
        db_session, user_id=seed_user, memory_id=memory_id
    )
    with pytest.raises(MemoryNotFoundError):
        await memory_service.get_memory(
            db_session, user_id=seed_user, memory_id=memory_id
        )
    # History survives a soft delete.
    versions = await repo.list_versions(db_session, memory_id=memory_id)
    assert len(versions) == 1


async def test_get_missing_raises_not_found(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    with pytest.raises(MemoryNotFoundError):
        await memory_service.get_memory(
            db_session, user_id=seed_user, memory_id=uuid.uuid4()
        )
