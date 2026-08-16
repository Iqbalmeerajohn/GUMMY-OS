"""The learned user profile: observation, trait derivation, and rendering."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory, MemoryStatus
from app.models.memory import Memory
from app.services.conversation.emotion import Mood, MoodReading
from app.services.memory import user_profile_service as profiles


def _memory(user_id: uuid.UUID, category: MemoryCategory, content: str) -> Memory:
    return Memory(
        user_id=user_id,
        category=category,
        content=content,
        importance_score=0.5,
        confidence_score=0.5,
        status=MemoryStatus.ACTIVE,
    )


@pytest.mark.asyncio
async def test_first_contact_creates_an_empty_profile(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    profile = await profiles.load(db_session, user_id=seed_user)
    assert profile.message_count == 0
    assert profile.traits == {}
    assert profiles.render(profile) is None


@pytest.mark.asyncio
async def test_observe_tracks_counters_and_rolling_mean(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    for message in ("ab", "abcd"):
        await profiles.observe(db_session, user_id=seed_user, message=message)
    profile = await profiles.load(db_session, user_id=seed_user)
    assert profile.message_count == 2
    assert profile.avg_message_chars == pytest.approx(3.0)
    assert profile.first_seen_at is not None
    assert profile.last_seen_at is not None


@pytest.mark.asyncio
async def test_neutral_messages_are_not_tallied_as_mood(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Neutral is the absence of evidence, not evidence of calm."""
    await profiles.observe(
        db_session,
        user_id=seed_user,
        message="list my files",
        mood=MoodReading(Mood.NEUTRAL, 0.0),
    )
    profile = await profiles.load(db_session, user_id=seed_user)
    assert profile.mood_counts == {}


@pytest.mark.asyncio
async def test_traits_are_derived_from_active_memories(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    db_session.add_all(
        [
            _memory(seed_user, MemoryCategory.PROFILE, "Name is Rehan"),
            _memory(seed_user, MemoryCategory.PROFILE, "Lives in Vizag"),
            _memory(seed_user, MemoryCategory.PROJECT, "Building GUMMY OS"),
        ]
    )
    await db_session.commit()

    profile = await profiles.refresh_traits(db_session, user_id=seed_user)
    assert profile.traits.get("name") == "Name is Rehan"
    assert profile.traits.get("location") == "Lives in Vizag"

    rendered = profiles.render(profile)
    assert rendered is not None
    assert "<learned_profile>" in rendered
    assert "Rehan" in rendered


@pytest.mark.asyncio
async def test_archived_memories_drop_out_of_the_portrait(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Deriving (not storing) traits is what keeps the portrait honest."""
    memory = _memory(seed_user, MemoryCategory.PROFILE, "Lives in Vizag")
    db_session.add(memory)
    await db_session.commit()

    profile = await profiles.refresh_traits(db_session, user_id=seed_user)
    assert "location" in profile.traits

    memory.status = MemoryStatus.ARCHIVED
    await db_session.commit()

    profile = await profiles.refresh_traits(db_session, user_id=seed_user)
    assert "location" not in profile.traits


@pytest.mark.asyncio
async def test_style_and_baseline_appear_only_with_enough_evidence(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    for _ in range(10):
        await profiles.observe(
            db_session,
            user_id=seed_user,
            message="fix the build",
            mood=MoodReading(Mood.STRESSED, 0.6),
        )
    profile = await profiles.load(db_session, user_id=seed_user)
    rendered = profiles.render(profile)
    assert rendered is not None
    assert "short fragments" in rendered
    assert "time pressure" in rendered
