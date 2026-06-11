"""Goal model — durable user intent the agent workforce advances (M8).

The persistent backbone that turns chat into sustained, multi-session work:
a goal is *what the user wants*; ``tasks`` decompose it into units of agent
work. Deliberately minimal (status + priority + hub context) — real agents
drive its evolution (PHASE3_PLAN.md §11).
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
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AgentContext, GoalStatus, enum_type

_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in GoalStatus)
_AGENT_CONTEXT_VALUES = ", ".join(f"'{a.value}'" for a in AgentContext)


class Goal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A durable, tenant-scoped goal."""

    __tablename__ = "goals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[GoalStatus] = mapped_column(
        enum_type(GoalStatus, "goal_status"),
        nullable=False,
        default=GoalStatus.ACTIVE,
        server_default=text("'active'"),
    )
    # Which hub the goal belongs to (the Phase 2 forward seam, reused).
    agent_context: Mapped[AgentContext] = mapped_column(
        enum_type(AgentContext, "goal_agent_context"),
        nullable=False,
        default=AgentContext.GENERAL,
        server_default=text("'general'"),
    )
    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    target_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_goals_user_id", "user_id"),
        Index("ix_goals_user_id_status", "user_id", "status"),
        CheckConstraint(
            f"status IN ({_STATUS_VALUES})",
            name="status_valid",
        ),
        CheckConstraint(
            f"agent_context IN ({_AGENT_CONTEXT_VALUES})",
            name="agent_context_valid",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Goal id={self.id} user_id={self.user_id} "
            f"status={self.status} title={self.title[:30]!r}>"
        )
