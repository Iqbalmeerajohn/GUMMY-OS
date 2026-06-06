"""Repository-layer tests (direct DB, no HTTP)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory, MemoryChangeReason, MemoryStatus
from app.repositories import memory_repository as repo


async def _new_memory(
    session: AsyncSession, user_id: uuid.UUID, content: str = "hello"
) -> uuid.UUID:
    memory = await repo.create_memory(
        session,
        user_id=user_id,
        category=MemoryCategory.PROFILE,
        content=content,
        importance_score=0.5,
        confidence_score=0.5,
    )
    await session.commit()
    return memory.id


async def test_create_and_get(db_session: AsyncSession, seed_user: uuid.UUID) -> None:
    memory_id = await _new_memory(db_session, seed_user)
    fetched = await repo.get_memory(db_session, memory_id=memory_id, user_id=seed_user)
    assert fetched is not None
    assert fetched.content == "hello"
    assert fetched.status is MemoryStatus.ACTIVE


async def test_get_is_tenant_scoped(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory_id = await _new_memory(db_session, seed_user)
    other_user = uuid.uuid4()
    assert (
        await repo.get_memory(db_session, memory_id=memory_id, user_id=other_user)
        is None
    )


async def test_list_pagination_and_total(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    for i in range(3):
        await _new_memory(db_session, seed_user, content=f"m{i}")
    items, total = await repo.list_memories(
        db_session, user_id=seed_user, limit=2, offset=0
    )
    assert total == 3
    assert len(items) == 2


async def test_update_fields(db_session: AsyncSession, seed_user: uuid.UUID) -> None:
    memory_id = await _new_memory(db_session, seed_user)
    memory = await repo.get_memory(db_session, memory_id=memory_id, user_id=seed_user)
    assert memory is not None
    await repo.update_memory(db_session, memory, content="updated")
    await db_session.commit()
    assert memory.content == "updated"


async def test_archive_sets_status(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory_id = await _new_memory(db_session, seed_user)
    memory = await repo.get_memory(db_session, memory_id=memory_id, user_id=seed_user)
    assert memory is not None
    await repo.archive_memory(db_session, memory)
    await db_session.commit()
    assert memory.status is MemoryStatus.ARCHIVED


async def test_soft_delete_excludes_from_get_and_list(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory_id = await _new_memory(db_session, seed_user)
    memory = await repo.get_memory(db_session, memory_id=memory_id, user_id=seed_user)
    assert memory is not None
    await repo.delete_memory(db_session, memory)
    await db_session.commit()

    assert (
        await repo.get_memory(db_session, memory_id=memory_id, user_id=seed_user)
        is None
    )
    _, total = await repo.list_memories(
        db_session, user_id=seed_user, limit=10, offset=0
    )
    assert total == 0
    # Still retrievable when explicitly including deleted rows.
    assert (
        await repo.get_memory(
            db_session,
            memory_id=memory_id,
            user_id=seed_user,
            include_deleted=True,
        )
        is not None
    )


async def test_versioning_helpers(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory_id = await _new_memory(db_session, seed_user)
    assert await repo.next_version_number(db_session, memory_id) == 1

    await repo.add_version(
        db_session,
        memory_id=memory_id,
        version_number=1,
        content_snapshot="hello",
        change_reason=MemoryChangeReason.CREATED,
    )
    await db_session.commit()

    assert await repo.next_version_number(db_session, memory_id) == 2
    versions = await repo.list_versions(db_session, memory_id=memory_id)
    assert len(versions) == 1
    assert versions[0].change_reason is MemoryChangeReason.CREATED
