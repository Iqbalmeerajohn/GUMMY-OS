"""Data-access layer for tasks (persistence only, no commit)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TaskStatus
from app.models.task import Task

# The states that count as "open" work for context packing.
OPEN_STATUSES = (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)


async def create_task(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    title: str,
    goal_id: uuid.UUID | None = None,
    agent_key: str | None = None,
    agent_run_id: uuid.UUID | None = None,
    seq: int = 0,
) -> Task:
    """Insert a new pending task and flush to populate id."""
    task = Task(
        user_id=user_id,
        title=title,
        goal_id=goal_id,
        agent_key=agent_key,
        agent_run_id=agent_run_id,
        seq=seq,
    )
    session.add(task)
    await session.flush()
    return task


async def get_task(
    session: AsyncSession,
    *,
    task_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Task | None:
    """Fetch a single tenant-scoped task by id, if it exists."""
    stmt = select(Task).where(Task.id == task_id, Task.user_id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_tasks(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    status: TaskStatus | None = None,
    goal_id: uuid.UUID | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Task], int]:
    """Return a page of tasks (seq asc, oldest first) and the total."""
    filters = [Task.user_id == user_id]
    if status is not None:
        filters.append(Task.status == status)
    if goal_id is not None:
        filters.append(Task.goal_id == goal_id)
    total = await session.scalar(select(func.count()).select_from(Task).where(*filters))
    stmt = (
        select(Task)
        .where(*filters)
        .order_by(Task.seq.asc(), Task.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), int(total or 0)


async def list_open(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
) -> list[Task]:
    """Pending/in-progress tasks for context packing (seq asc)."""
    stmt = (
        select(Task)
        .where(Task.user_id == user_id, Task.status.in_(OPEN_STATUSES))
        .order_by(Task.seq.asc(), Task.created_at.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
