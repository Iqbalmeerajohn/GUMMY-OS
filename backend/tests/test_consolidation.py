"""Memory consolidation — one true fact per thing GUMMY knows.

Trigram similarity is a Postgres feature, so on the SQLite suite consolidation
degrades to exact normalized matching. These tests pin the behaviour that holds
on both: restatements reinforce, distinct facts are stored, and a retired memory
stops influencing answers.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory, MemoryStatus
from app.models.memory import Memory
from app.services.memory import consolidation
from app.services.memory.consolidation import Resolution


def _memory(user_id: uuid.UUID, content: str) -> Memory:
    return Memory(
        user_id=user_id,
        category=MemoryCategory.PROFILE,
        content=content,
        importance_score=0.5,
        confidence_score=0.5,
        status=MemoryStatus.ACTIVE,
    )


def test_normalization_ignores_case_and_punctuation() -> None:
    assert consolidation.normalize("Lives in Vizag.") == consolidation.normalize(
        "lives in vizag"
    )


@pytest.mark.asyncio
async def test_a_restatement_is_a_duplicate(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    db_session.add(_memory(seed_user, "Lives in Vizag"))
    await db_session.commit()

    decision = await consolidation.resolve(
        db_session,
        user_id=seed_user,
        category=MemoryCategory.PROFILE,
        content="lives in vizag.",
    )
    assert decision.resolution is Resolution.DUPLICATE
    assert decision.existing is not None


@pytest.mark.asyncio
async def test_a_different_fact_is_new(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    db_session.add(_memory(seed_user, "Lives in Vizag"))
    await db_session.commit()

    decision = await consolidation.resolve(
        db_session,
        user_id=seed_user,
        category=MemoryCategory.PROFILE,
        content="Name is Rehan",
    )
    assert decision.resolution is Resolution.NEW


@pytest.mark.asyncio
async def test_another_users_memories_are_invisible(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Consolidation must never reach across tenants to find a duplicate."""
    db_session.add(_memory(uuid.uuid4(), "Lives in Vizag"))
    await db_session.commit()

    decision = await consolidation.resolve(
        db_session,
        user_id=seed_user,
        category=MemoryCategory.PROFILE,
        content="Lives in Vizag",
    )
    assert decision.resolution is Resolution.NEW


def test_reinforcement_raises_confidence_faster_than_importance() -> None:
    memory = _memory(uuid.uuid4(), "Lives in Vizag")
    before_confidence = memory.confidence_score
    before_importance = memory.importance_score

    consolidation.reinforce(memory)

    gained_confidence = memory.confidence_score - before_confidence
    gained_importance = memory.importance_score - before_importance
    assert gained_confidence > gained_importance > 0


def test_reinforcement_is_clamped() -> None:
    """A chatty topic must not be able to saturate the ranking."""
    memory = _memory(uuid.uuid4(), "Lives in Vizag")
    for _ in range(100):
        consolidation.reinforce(memory)
    assert memory.confidence_score == 1.0
    assert memory.importance_score == 1.0


def test_superseding_retires_rather_than_deletes() -> None:
    memory = _memory(uuid.uuid4(), "Lives in Vizag")
    consolidation.supersede(memory)
    assert memory.status is MemoryStatus.SUPERSEDED
    assert memory.deleted_at is None
