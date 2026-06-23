"""Goal model — a durable, user-facing objective (M5 Goals System).

A goal is *what the user wants to achieve*. It carries a lifecycle status,
a user-assigned priority, an optional category and target date, and a
progress percentage. Progress is **derived from milestones** when a goal has
any (see :mod:`app.services.goals.milestone_service`); goals without
milestones fall back to a manually-set ``progress_percentage``.

``agent_context`` (the Phase 2 hub seam) is retained so a goal can be tied to
a workspace hub and surfaced to the matching agent.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    AgentContext,
    GoalPriority,
    GoalStatus,
    enum_type,
)
from app.models.goal_milestone import GoalMilestone

_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in GoalStatus)
_PRIORITY_VALUES = ", ".join(f"'{p.value}'" for p in GoalPriority)
_AGENT_CONTEXT_VALUES = ", ".join(f"'{a.value}'" for a in AgentContext)

# Goal title / category bounds (also enforced at the schema edge).
GOAL_CATEGORY_MAX_LENGTH = 64


class Goal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A durable, tenant-scoped goal with milestones and derived progress."""

    __tablename__ = "goals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[GoalStatus] = mapped_column(
        enum_type(GoalStatus, "goal_status"),
        nullable=False,
        default=GoalStatus.ACTIVE,
        server_default=text("'active'"),
    )
    priority: Mapped[GoalPriority] = mapped_column(
        enum_type(GoalPriority, "goal_priority"),
        nullable=False,
        default=GoalPriority.MEDIUM,
        server_default=text("'medium'"),
    )
    # Which hub the goal belongs to (the Phase 2 forward seam, reused).
    agent_context: Mapped[AgentContext] = mapped_column(
        enum_type(AgentContext, "goal_agent_context"),
        nullable=False,
        default=AgentContext.GENERAL,
        server_default=text("'general'"),
    )
    # 0–100. Authoritative only when the goal has no milestones; otherwise it
    # is recomputed from milestone completion by the service layer.
    progress_percentage: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    target_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    milestones: Mapped[list[GoalMilestone]] = relationship(
        back_populates="goal",
        cascade="all, delete-orphan",
        order_by="GoalMilestone.order_index, GoalMilestone.created_at",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_goals_user_id", "user_id"),
        Index("ix_goals_user_id_status", "user_id", "status"),
        CheckConstraint(
            f"status IN ({_STATUS_VALUES})",
            name="status_valid",
        ),
        CheckConstraint(
            f"priority IN ({_PRIORITY_VALUES})",
            name="priority_valid",
        ),
        CheckConstraint(
            f"agent_context IN ({_AGENT_CONTEXT_VALUES})",
            name="agent_context_valid",
        ),
        CheckConstraint(
            "progress_percentage >= 0 AND progress_percentage <= 100",
            name="progress_percentage_range",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Goal id={self.id} user_id={self.user_id} "
            f"status={self.status} title={self.title[:30]!r}>"
        )
