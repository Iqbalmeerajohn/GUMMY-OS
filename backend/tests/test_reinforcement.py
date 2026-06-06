"""Reinforcement tests (SQLite): cooldown, diminishing bumps, caps."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory
from app.models.memory import Memory
from app.repositories import memory_repository as repo
from app.services.memory.memory_retrieval_service import reinforce_memories


async def _make_memory(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    importance: float = 0.5,
    confidence: float = 0.5,
) -> Memory:
    memory = await repo.create_memory(
        session,
        user_id=user_id,
        category=MemoryCategory.CAREER,
        content="Targeting Qualcomm",
        importance_score=importance,
        confidence_score=confidence,
    )
    await session.commit()
    return memory


async def test_first_reinforcement_bumps_and_counts(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory = await _make_memory(db_session, seed_user)
    now = datetime(2026, 6, 7, tzinfo=UTC)

    await reinforce_memories(db_session, [memory], now=now)
    await db_session.commit()

    assert memory.recall_count == 1
    assert memory.importance_score == 0.5 + 0.05 * 0.5
    assert memory.confidence_score == 0.5 + 0.03 * 0.5
    assert memory.last_recalled_at is not None


async def test_cooldown_blocks_burst_inflation(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory = await _make_memory(db_session, seed_user)
    t0 = datetime(2026, 6, 7, 12, 0, 0, tzinfo=UTC)

    await reinforce_memories(db_session, [memory], now=t0)
    bumped_importance = memory.importance_score

    # Within the cooldown window: counts the recall, but no score bump.
    await reinforce_memories(db_session, [memory], now=t0 + timedelta(seconds=30))
    assert memory.recall_count == 2
    assert memory.importance_score == bumped_importance

    # Past the cooldown: bumps again.
    await reinforce_memories(db_session, [memory], now=t0 + timedelta(seconds=120))
    assert memory.recall_count == 3
    assert memory.importance_score > bumped_importance


async def test_scores_are_capped_at_one(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory = await _make_memory(db_session, seed_user, importance=1.0, confidence=1.0)
    now = datetime(2026, 6, 7, tzinfo=UTC)

    await reinforce_memories(db_session, [memory], now=now)
    assert memory.importance_score == 1.0
    assert memory.confidence_score == 1.0
