"""Task model — one unit of agent work, optionally under a goal (M8).

``goal_id`` and ``agent_run_id`` are ``ON DELETE SET NULL`` so durable work
records survive goal/run cleanup (provenance without coupling).
``agent_run_id`` ties a task to the orchestration that produced/advanced it.
See PHASE3_PLAN.md §11.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TaskStatus, enum_type

_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in TaskStatus)


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant-scoped unit of work with status and ordering."""

    __tablename__ = "tasks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    goal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Which agent the task is for/by (key into the registry), if any.
    agent_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        enum_type(TaskStatus, "task_status"),
        nullable=False,
        default=TaskStatus.PENDING,
        server_default=text("'pending'"),
    )
    # Loose ordering among sibling tasks (not unique by design).
    seq: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    # Compact pointer/preview of the task's outcome.
    result_ref: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_tasks_user_id", "user_id"),
        Index("ix_tasks_user_id_status", "user_id", "status"),
        Index("ix_tasks_goal_id", "goal_id"),
        CheckConstraint(
            f"status IN ({_STATUS_VALUES})",
            name="status_valid",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Task id={self.id} user_id={self.user_id} "
            f"status={self.status} title={self.title[:30]!r}>"
        )
