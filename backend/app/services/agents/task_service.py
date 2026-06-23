"""Task service — units of agent work with guarded transitions (M8).

Owns validation and the unit of work (commit); the repository flushes.
``flush_only=True`` lets the Orchestrator create/advance tasks inside the
turn's single transaction (run_turn commits) — the API paths commit here.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.enums import TaskStatus
from app.models.task import Task
from app.repositories import task_repository as repo
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.goals.goal_service import EmptyUpdateError, get_goal

# Terminal states: no transition out.
_TERMINAL = (TaskStatus.DONE, TaskStatus.CANCELLED)


class TaskNotFoundError(AppError):
    """Raised when a task does not exist for this tenant."""

    def __init__(self, task_id: uuid.UUID) -> None:
        super().__init__(
            f"Task {task_id} not found.",
            code="task_not_found",
            status_code=404,
        )


class InvalidTaskTransitionError(AppError):
    """Raised on a status change a task's lifecycle forbids."""

    def __init__(self, current: TaskStatus, target: TaskStatus) -> None:
        super().__init__(
            f"Cannot move a {current.value} task to {target.value}.",
            code="invalid_task_transition",
            status_code=409,
        )


def _guard_transition(current: TaskStatus, target: TaskStatus) -> None:
    if current == target:
        return
    if current in _TERMINAL:
        raise InvalidTaskTransitionError(current, target)


async def create_task(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    payload: TaskCreate,
    agent_run_id: uuid.UUID | None = None,
    flush_only: bool = False,
) -> Task:
    """Create a pending task (goal ownership enforced when linked)."""
    if payload.goal_id is not None:
        # 404 if the goal is not this tenant's.
        await get_goal(session, user_id=user_id, goal_id=payload.goal_id)
    task = await repo.create_task(
        session,
        user_id=user_id,
        title=payload.title,
        goal_id=payload.goal_id,
        agent_key=payload.agent_key,
        agent_run_id=agent_run_id,
        seq=payload.seq,
    )
    if not flush_only:
        await session.commit()
        await session.refresh(task)
    return task


async def get_task(
    session: AsyncSession, *, user_id: uuid.UUID, task_id: uuid.UUID
) -> Task:
    """Fetch one task or raise 404."""
    task = await repo.get_task(session, task_id=task_id, user_id=user_id)
    if task is None:
        raise TaskNotFoundError(task_id)
    return task


async def list_tasks(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    status: TaskStatus | None = None,
    goal_id: uuid.UUID | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Task], int]:
    """List tasks (seq asc, oldest first)."""
    return await repo.list_tasks(
        session,
        user_id=user_id,
        status=status,
        goal_id=goal_id,
        limit=limit,
        offset=offset,
    )


async def update_task(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
    payload: TaskUpdate,
) -> Task:
    """Apply a partial update with transition guards. Commits."""
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise EmptyUpdateError()
    task = await get_task(session, user_id=user_id, task_id=task_id)
    if "status" in changes:
        _guard_transition(task.status, changes["status"])
    if changes.get("goal_id") is not None:
        await get_goal(session, user_id=user_id, goal_id=changes["goal_id"])
    for field, value in changes.items():
        setattr(task, field, value)
    await session.commit()
    await session.refresh(task)
    return task


async def advance_task(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
    flush_only: bool = False,
) -> Task:
    """Move a task one step forward: pending → in_progress → done."""
    task = await get_task(session, user_id=user_id, task_id=task_id)
    if task.status == TaskStatus.PENDING:
        task.status = TaskStatus.IN_PROGRESS
    elif task.status in (TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED):
        task.status = TaskStatus.DONE
    else:
        raise InvalidTaskTransitionError(task.status, TaskStatus.DONE)
    if not flush_only:
        await session.commit()
        await session.refresh(task)
    else:
        await session.flush()
    return task


async def block_task(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
    flush_only: bool = False,
) -> Task:
    """Mark an open task blocked."""
    task = await get_task(session, user_id=user_id, task_id=task_id)
    if task.status in _TERMINAL:
        raise InvalidTaskTransitionError(task.status, TaskStatus.BLOCKED)
    task.status = TaskStatus.BLOCKED
    if not flush_only:
        await session.commit()
        await session.refresh(task)
    else:
        await session.flush()
    return task


async def complete_task(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    task_id: uuid.UUID,
    result_ref: dict | None = None,
    flush_only: bool = False,
) -> Task:
    """Mark a non-terminal task done (optionally recording its outcome)."""
    task = await get_task(session, user_id=user_id, task_id=task_id)
    if task.status in _TERMINAL:
        raise InvalidTaskTransitionError(task.status, TaskStatus.DONE)
    task.status = TaskStatus.DONE
    if result_ref is not None:
        task.result_ref = result_ref
    if not flush_only:
        await session.commit()
        await session.refresh(task)
    else:
        await session.flush()
    return task
