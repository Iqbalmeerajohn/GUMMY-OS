"""GoalMilestone model — a checklist step under a goal (M5 Goals System).

Milestones decompose a goal into concrete, user-managed steps. The count of
completed vs. total milestones is what drives a goal's derived progress
(``goal.progress_percentage``). ``order_index`` gives a stable, user-defined
ordering. ``user_id`` is denormalized so the same fail-closed, direct-column
RLS policy used across the schema applies without a join.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.goal import Goal

# Milestone title bound (also enforced at the schema edge).
MILESTONE_TITLE_MAX_LENGTH = 200


class GoalMilestone(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant-scoped, ordered checklist step belonging to one goal."""

    __tablename__ = "goal_milestones"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    goal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # Stable user-defined ordering among sibling milestones (not unique).
    order_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    goal: Mapped[Goal] = relationship(back_populates="milestones")

    __table_args__ = (
        Index("ix_goal_milestones_user_id", "user_id"),
        Index("ix_goal_milestones_goal_id", "goal_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<GoalMilestone id={self.id} goal_id={self.goal_id} "
            f"completed={self.completed} title={self.title[:30]!r}>"
        )
