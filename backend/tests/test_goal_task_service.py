"""Goal & Task repository/service tests (Phase 3, M8)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    AgentContext,
    GoalPriority,
    GoalStatus,
    TaskStatus,
)
from app.models.user import User
from app.repositories import goal_repository, task_repository
from app.schemas.goal import GoalCreate, GoalUpdate
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.agents import task_service
from app.services.agents.task_service import (
    InvalidTaskTransitionError,
    TaskNotFoundError,
)
from app.services.goals import goal_service
from app.services.goals.goal_service import (
    EmptyUpdateError,
    GoalNotFoundError,
)


async def _second_user(session: AsyncSession) -> uuid.UUID:
    other = User(email=f"other-{uuid.uuid4().hex[:8]}@example.com")
    session.add(other)
    await session.commit()
    return other.id


# ── goals ─────────────────────────────────────────────────────────────────────


async def test_goal_crud_lifecycle(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    goal = await goal_service.create_goal(
        db_session,
        user_id=seed_user,
        payload=GoalCreate(
            title="Land a Qualcomm offer",
            description="systems role",
            category="career",
            agent_context=AgentContext.CAREER,
            priority=GoalPriority.HIGH,
        ),
    )
    assert goal.status == GoalStatus.ACTIVE
    assert goal.agent_context == AgentContext.CAREER
    assert goal.priority == GoalPriority.HIGH
    assert goal.category == "career"

    updated = await goal_service.update_goal(
        db_session,
        user_id=seed_user,
        goal_id=goal.id,
        payload=GoalUpdate(priority=GoalPriority.LOW, progress_percentage=30),
    )
    assert updated.priority == GoalPriority.LOW
    assert updated.progress_percentage == 30

    done = await goal_service.complete_goal(
        db_session, user_id=seed_user, goal_id=goal.id
    )
    assert done.status == GoalStatus.COMPLETED
    assert done.completed_at is not None

    archived = await goal_service.archive_goal(
        db_session, user_id=seed_user, goal_id=goal.id
    )
    assert archived.status == GoalStatus.ARCHIVED
    # Leaving the completed state clears the completion timestamp.
    assert archived.completed_at is None


async def test_goal_empty_update_rejected(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    goal = await goal_service.create_goal(
        db_session, user_id=seed_user, payload=GoalCreate(title="g")
    )
    with pytest.raises(EmptyUpdateError):
        await goal_service.update_goal(
            db_session,
            user_id=seed_user,
            goal_id=goal.id,
            payload=GoalUpdate(),
        )


async def test_goal_foreign_tenant_404(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    other = await _second_user(db_session)
    goal = await goal_service.create_goal(
        db_session, user_id=seed_user, payload=GoalCreate(title="mine")
    )
    with pytest.raises(GoalNotFoundError):
        await goal_service.get_goal(db_session, user_id=other, goal_id=goal.id)
    items, total = await goal_service.list_goals(
        db_session, user_id=other, limit=10, offset=0
    )
    assert (items, total) == ([], 0)


async def test_goal_list_filters_and_ordering(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    low = await goal_service.create_goal(
        db_session,
        user_id=seed_user,
        payload=GoalCreate(title="low", priority=GoalPriority.LOW),
    )
    high = await goal_service.create_goal(
        db_session,
        user_id=seed_user,
        payload=GoalCreate(title="high", priority=GoalPriority.HIGH),
    )
    await goal_service.update_goal(
        db_session,
        user_id=seed_user,
        goal_id=low.id,
        payload=GoalUpdate(status=GoalStatus.ARCHIVED),
    )
    active, total = await goal_service.list_goals(
        db_session,
        user_id=seed_user,
        status=GoalStatus.ACTIVE,
        limit=10,
        offset=0,
    )
    assert total == 1
    assert active[0].id == high.id
    everything, total_all = await goal_service.list_goals(
        db_session, user_id=seed_user, limit=10, offset=0
    )
    assert total_all == 2
    assert [g.id for g in everything] == [high.id, low.id]  # priority desc


# ── tasks ─────────────────────────────────────────────────────────────────────


async def test_task_create_with_goal_linkage_and_run_provenance(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    from app.repositories import agent_run_repository as run_repo

    goal = await goal_service.create_goal(
        db_session, user_id=seed_user, payload=GoalCreate(title="g")
    )
    run = await run_repo.create_run(db_session, user_id=seed_user)
    task = await task_service.create_task(
        db_session,
        user_id=seed_user,
        payload=TaskCreate(title="t", goal_id=goal.id, agent_key="general"),
        agent_run_id=run.id,
    )
    assert task.status == TaskStatus.PENDING
    assert task.goal_id == goal.id
    assert task.agent_run_id == run.id


async def test_task_rejects_foreign_goal(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    other = await _second_user(db_session)
    goal = await goal_service.create_goal(
        db_session, user_id=seed_user, payload=GoalCreate(title="mine")
    )
    with pytest.raises(GoalNotFoundError):
        await task_service.create_task(
            db_session,
            user_id=other,
            payload=TaskCreate(title="forged", goal_id=goal.id),
        )


async def test_task_advance_block_complete_transitions(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    task = await task_service.create_task(
        db_session, user_id=seed_user, payload=TaskCreate(title="t")
    )
    advanced = await task_service.advance_task(
        db_session, user_id=seed_user, task_id=task.id
    )
    assert advanced.status == TaskStatus.IN_PROGRESS
    blocked = await task_service.block_task(
        db_session, user_id=seed_user, task_id=task.id
    )
    assert blocked.status == TaskStatus.BLOCKED
    completed = await task_service.complete_task(
        db_session,
        user_id=seed_user,
        task_id=task.id,
        result_ref={"note": "done by test"},
    )
    assert completed.status == TaskStatus.DONE
    assert completed.result_ref == {"note": "done by test"}


async def test_task_terminal_states_are_final(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    task = await task_service.create_task(
        db_session, user_id=seed_user, payload=TaskCreate(title="t")
    )
    await task_service.update_task(
        db_session,
        user_id=seed_user,
        task_id=task.id,
        payload=TaskUpdate(status=TaskStatus.CANCELLED),
    )
    with pytest.raises(InvalidTaskTransitionError):
        await task_service.advance_task(db_session, user_id=seed_user, task_id=task.id)
    with pytest.raises(InvalidTaskTransitionError):
        await task_service.update_task(
            db_session,
            user_id=seed_user,
            task_id=task.id,
            payload=TaskUpdate(status=TaskStatus.PENDING),
        )


async def test_task_foreign_tenant_404_and_scoped_lists(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    other = await _second_user(db_session)
    task = await task_service.create_task(
        db_session, user_id=seed_user, payload=TaskCreate(title="mine")
    )
    with pytest.raises(TaskNotFoundError):
        await task_service.get_task(db_session, user_id=other, task_id=task.id)
    items, total = await task_service.list_tasks(
        db_session, user_id=other, limit=10, offset=0
    )
    assert (items, total) == ([], 0)


async def test_open_and_active_context_listings(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    await goal_service.create_goal(
        db_session, user_id=seed_user, payload=GoalCreate(title="active")
    )
    done_goal = await goal_service.create_goal(
        db_session, user_id=seed_user, payload=GoalCreate(title="done")
    )
    await goal_service.complete_goal(
        db_session, user_id=seed_user, goal_id=done_goal.id
    )
    open_task = await task_service.create_task(
        db_session, user_id=seed_user, payload=TaskCreate(title="open")
    )
    closed = await task_service.create_task(
        db_session, user_id=seed_user, payload=TaskCreate(title="closed")
    )
    await task_service.complete_task(db_session, user_id=seed_user, task_id=closed.id)

    goals = await goal_repository.list_active(db_session, user_id=seed_user, limit=10)
    assert [g.title for g in goals] == ["active"]
    tasks = await task_repository.list_open(db_session, user_id=seed_user, limit=10)
    assert [t.id for t in tasks] == [open_task.id]
