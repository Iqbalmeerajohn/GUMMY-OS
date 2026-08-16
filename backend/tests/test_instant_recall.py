"""Instant recall — the sub-second path that answers without a model.

The tests that matter most here are the *declines*: falling through costs one
cheap lookup, while a confidently wrong instant answer is a visible failure.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory, MemoryStatus
from app.models.memory import Memory
from app.services.memory import instant_recall


def _memory(user_id: uuid.UUID, category: MemoryCategory, content: str) -> Memory:
    return Memory(
        user_id=user_id,
        category=category,
        content=content,
        importance_score=0.5,
        confidence_score=0.5,
        status=MemoryStatus.ACTIVE,
    )


def test_recognises_a_direct_question() -> None:
    intent = instant_recall.detect_intent("what's my name?")
    assert intent is not None
    assert intent.key == "name"


def test_a_long_request_that_merely_mentions_a_fact_is_not_a_question() -> None:
    """'Write a bio using my name and city' wants generation, not recall."""
    assert (
        instant_recall.detect_intent(
            "write a short cover letter using my name and the job description below"
        )
        is None
    )


@pytest.mark.asyncio
async def test_answers_from_a_stored_fact(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    db_session.add(_memory(seed_user, MemoryCategory.PROFILE, "Name is Rehan"))
    await db_session.commit()

    answer = await instant_recall.try_answer(
        db_session, user_id=seed_user, message="what is my name?"
    )
    assert answer is not None
    assert "Rehan" in answer.text
    assert answer.intent_key == "name"


@pytest.mark.asyncio
async def test_declines_when_two_facts_answer_equally_well(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """A tie is ambiguity; the model reconciles it instead of us guessing."""
    db_session.add_all(
        [
            _memory(seed_user, MemoryCategory.PROFILE, "Lives in Vizag"),
            _memory(seed_user, MemoryCategory.PROFILE, "Lives in Bangalore"),
        ]
    )
    await db_session.commit()

    assert (
        await instant_recall.try_answer(
            db_session, user_id=seed_user, message="where do I live?"
        )
        is None
    )


@pytest.mark.asyncio
async def test_declines_when_nothing_is_stored(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    assert (
        await instant_recall.try_answer(
            db_session, user_id=seed_user, message="what is my name?"
        )
        is None
    )


@pytest.mark.asyncio
async def test_archived_facts_are_never_used(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    stale = _memory(seed_user, MemoryCategory.PROFILE, "Name is Rehan")
    stale.status = MemoryStatus.SUPERSEDED
    db_session.add(stale)
    await db_session.commit()

    assert (
        await instant_recall.try_answer(
            db_session, user_id=seed_user, message="what is my name?"
        )
        is None
    )
