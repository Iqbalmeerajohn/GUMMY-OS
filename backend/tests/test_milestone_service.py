"""Milestone service + derived-progress tests (M5 Goals System)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.goal import GoalCreate, GoalUpdate, MilestoneCreate, MilestoneUpdate
from app.services.goals import goal_service, milestone_service
from app.services.goals.milestone_service import (
    EmptyMilestoneUpdateError,
    MilestoneNotFoundError,
)


async def _second_user(session: AsyncSession) -> uuid.UUID:
    other = User(email=f"other-{uuid.uuid4().hex[:8]}@example.com")
    session.add(other)
    await session.commit()
    return other.id


async def _goal(session: AsyncSession, user_id: uuid.UUID, title: str = "g"):
    return await goal_service.create_goal(
        session, user_id=user_id, payload=GoalCreate(title=title)
    )


async def test_progress_auto_calculates_from_milestones(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    goal = await _goal(db_session, seed_user)
    milestones = []
    for i in range(5):
        milestones.append(
            await milestone_service.add_milestone(
                db_session,
                user_id=seed_user,
                goal_id=goal.id,
                payload=MilestoneCreate(title=f"step {i}"),
            )
        )
    # order_index is assigned sequentially.
    assert [m.order_index for m in milestones] == [0, 1, 2, 3, 4]

    refreshed = await goal_service.get_goal(
        db_session, user_id=seed_user, goal_id=goal.id
    )
    assert refreshed.progress_percentage == 0

    for m in milestones[:2]:
        await milestone_service.update_milestone(
            db_session,
            user_id=seed_user,
            milestone_id=m.id,
            payload=MilestoneUpdate(completed=True),
        )

    # 2 of 5 complete → 40%.
    refreshed = await goal_service.get_goal(
        db_session, user_id=seed_user, goal_id=goal.id
    )
    assert refreshed.progress_percentage == 40


async def test_completing_milestone_stamps_timestamp(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    goal = await _goal(db_session, seed_user)
    milestone = await milestone_service.add_milestone(
        db_session,
        user_id=seed_user,
        goal_id=goal.id,
        payload=MilestoneCreate(title="ship it"),
    )
    assert milestone.completed is False
    assert milestone.completed_at is None

    done = await milestone_service.update_milestone(
        db_session,
        user_id=seed_user,
        milestone_id=milestone.id,
        payload=MilestoneUpdate(completed=True),
    )
    assert done.completed is True
    assert done.completed_at is not None

    reopened = await milestone_service.update_milestone(
        db_session,
        user_id=seed_user,
        milestone_id=milestone.id,
        payload=MilestoneUpdate(completed=False),
    )
    assert reopened.completed is False
    assert reopened.completed_at is None


async def test_manual_progress_for_goal_without_milestones(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    goal = await _goal(db_session, seed_user)
    updated = await goal_service.update_goal(
        db_session,
        user_id=seed_user,
        goal_id=goal.id,
        payload=GoalUpdate(progress_percentage=75),
    )
    assert updated.progress_percentage == 75


async def test_manual_progress_ignored_when_milestones_exist(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    goal = await _goal(db_session, seed_user)
    await milestone_service.add_milestone(
        db_session,
        user_id=seed_user,
        goal_id=goal.id,
        payload=MilestoneCreate(title="only step"),
    )
    # Milestone-derived progress (0%) wins over the manual override.
    updated = await goal_service.update_goal(
        db_session,
        user_id=seed_user,
        goal_id=goal.id,
        payload=GoalUpdate(progress_percentage=90),
    )
    assert updated.progress_percentage == 0


async def test_deleting_milestone_recomputes_progress(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    goal = await _goal(db_session, seed_user)
    keep = await milestone_service.add_milestone(
        db_session,
        user_id=seed_user,
        goal_id=goal.id,
        payload=MilestoneCreate(title="keep"),
    )
    drop = await milestone_service.add_milestone(
        db_session,
        user_id=seed_user,
        goal_id=goal.id,
        payload=MilestoneCreate(title="drop"),
    )
    await milestone_service.update_milestone(
        db_session,
        user_id=seed_user,
        milestone_id=keep.id,
        payload=MilestoneUpdate(completed=True),
    )
    # 1 of 2 done → 50%.
    refreshed = await goal_service.get_goal(
        db_session, user_id=seed_user, goal_id=goal.id
    )
    assert refreshed.progress_percentage == 50

    await milestone_service.delete_milestone(
        db_session, user_id=seed_user, milestone_id=drop.id
    )
    # 1 of 1 done → 100%.
    refreshed = await goal_service.get_goal(
        db_session, user_id=seed_user, goal_id=goal.id
    )
    assert refreshed.progress_percentage == 100


async def test_empty_milestone_update_rejected(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    goal = await _goal(db_session, seed_user)
    milestone = await milestone_service.add_milestone(
        db_session,
        user_id=seed_user,
        goal_id=goal.id,
        payload=MilestoneCreate(title="m"),
    )
    with pytest.raises(EmptyMilestoneUpdateError):
        await milestone_service.update_milestone(
            db_session,
            user_id=seed_user,
            milestone_id=milestone.id,
            payload=MilestoneUpdate(),
        )


async def test_milestone_foreign_tenant_404(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    other = await _second_user(db_session)
    goal = await _goal(db_session, seed_user)
    milestone = await milestone_service.add_milestone(
        db_session,
        user_id=seed_user,
        goal_id=goal.id,
        payload=MilestoneCreate(title="mine"),
    )
    with pytest.raises(MilestoneNotFoundError):
        await milestone_service.get_milestone(
            db_session, user_id=other, milestone_id=milestone.id
        )


async def test_add_milestone_to_foreign_goal_404(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    other = await _second_user(db_session)
    goal = await _goal(db_session, seed_user)
    with pytest.raises(goal_service.GoalNotFoundError):
        await milestone_service.add_milestone(
            db_session,
            user_id=other,
            goal_id=goal.id,
            payload=MilestoneCreate(title="forged"),
        )
