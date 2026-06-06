"""Automatic embedding sync: create/update enqueue an embedding job."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory
from app.schemas.memory import MemoryCreate, MemoryUpdate
from app.services.memory import memory_service
from app.workers import embedding_worker as worker_module


async def test_create_enqueues_embedding(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[uuid.UUID, uuid.UUID]] = []
    monkeypatch.setattr(
        worker_module.embedding_worker,
        "enqueue",
        lambda memory_id, user_id: calls.append((memory_id, user_id)),
    )

    memory = await memory_service.create_memory(
        db_session,
        user_id=seed_user,
        payload=MemoryCreate(
            category=MemoryCategory.CAREER, content="Targeting Qualcomm"
        ),
    )

    assert calls == [(memory.id, seed_user)]


async def test_update_enqueues_embedding(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = await memory_service.create_memory(
        db_session,
        user_id=seed_user,
        payload=MemoryCreate(
            category=MemoryCategory.CAREER, content="Targeting Qualcomm"
        ),
    )

    calls: list[tuple[uuid.UUID, uuid.UUID]] = []
    monkeypatch.setattr(
        worker_module.embedding_worker,
        "enqueue",
        lambda memory_id, user_id: calls.append((memory_id, user_id)),
    )

    await memory_service.update_memory(
        db_session,
        user_id=seed_user,
        memory_id=memory.id,
        payload=MemoryUpdate(content="Targeting NVIDIA"),
    )

    assert calls == [(memory.id, seed_user)]
