"""Automation models — scheduled work that survives a restart.

Two tables, and the second is the interesting one.

``automations`` is the definition: what to do, when, and whether it is still
active. ``automation_runs`` is one row per *firing*, with a unique constraint on
``(automation_id, scheduled_for)``.

That constraint is the idempotency mechanism. A scheduler that stores "next run"
on the definition alone will double-fire whenever two workers race, a restart
replays a window, or a clock adjustment moves time backwards — and a duplicate
reminder is exactly the failure a user notices. Claiming a run means inserting
its row; the database refuses the second insert, so only one worker can proceed.
Correctness comes from a constraint rather than from careful sequencing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    AutomationKind,
    AutomationRunStatus,
    AutomationSchedule,
    AutomationStatus,
    enum_type,
)

if TYPE_CHECKING:
    from app.models.user import User

_KIND_VALUES = ", ".join(f"'{k.value}'" for k in AutomationKind)
_SCHEDULE_VALUES = ", ".join(f"'{s.value}'" for s in AutomationSchedule)
_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in AutomationStatus)
_RUN_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in AutomationRunStatus)


class Automation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A recurring or one-off task GUMMY runs on the user's behalf."""

    __tablename__ = "automations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[AutomationKind] = mapped_column(
        enum_type(AutomationKind, "automation_kind"), nullable=False
    )
    schedule: Mapped[AutomationSchedule] = mapped_column(
        enum_type(AutomationSchedule, "automation_schedule"), nullable=False
    )
    status: Mapped[AutomationStatus] = mapped_column(
        enum_type(AutomationStatus, "automation_status"),
        nullable=False,
        default=AutomationStatus.ACTIVE,
        server_default=text("'active'"),
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # IANA name, stored so a daily 9am reminder stays 9am for the person who
    # asked for it rather than 9am UTC. Scheduling arithmetic is done in UTC.
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'UTC'")
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Consecutive failures. A automation that keeps failing is parked rather
    # than retried forever — an endlessly erroring reminder is noise, not
    # resilience.
    failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # Kind-specific detail (the reminder text, the goal id, …). Free-form
    # because each kind needs different fields, validated by its executor.
    payload: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    user: Mapped[User] = relationship()
    runs: Mapped[list[AutomationRun]] = relationship(
        back_populates="automation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_automations_user_id", "user_id"),
        # The scheduler's only query: due, active, enabled. Partial so it stays
        # small however many completed automations accumulate.
        Index(
            "ix_automations_due",
            "next_run_at",
            postgresql_where=text("enabled AND status = 'active'"),
        ),
        CheckConstraint(f"kind IN ({_KIND_VALUES})", name="automation_kind_valid"),
        CheckConstraint(
            f"schedule IN ({_SCHEDULE_VALUES})", name="automation_schedule_valid"
        ),
        CheckConstraint(
            f"status IN ({_STATUS_VALUES})", name="automation_status_valid"
        ),
    )

    def __repr__(self) -> str:
        return f"<Automation id={self.id} kind={self.kind} status={self.status}>"


class AutomationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One firing of an automation.

    ``(automation_id, scheduled_for)`` is unique: claiming a run means inserting
    this row, so a duplicate claim is a constraint violation rather than a
    duplicate reminder.
    """

    __tablename__ = "automation_runs"

    automation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # The slot this run belongs to, not when it actually started. A run delayed
    # by a restart still belongs to the slot it was due for, which is what makes
    # the uniqueness meaningful across downtime.
    scheduled_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[AutomationRunStatus] = mapped_column(
        enum_type(AutomationRunStatus, "automation_run_status"),
        nullable=False,
        default=AutomationRunStatus.RUNNING,
        server_default=text("'running'"),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    automation: Mapped[Automation] = relationship(back_populates="runs")

    __table_args__ = (
        UniqueConstraint(
            "automation_id",
            "scheduled_for",
            name="uq_automation_runs_automation_id_scheduled_for",
        ),
        Index("ix_automation_runs_user_id", "user_id"),
        Index("ix_automation_runs_automation_id", "automation_id"),
        CheckConstraint(
            f"status IN ({_RUN_STATUS_VALUES})", name="automation_run_status_valid"
        ),
    )

    def __repr__(self) -> str:
        return f"<AutomationRun id={self.id} status={self.status}>"
