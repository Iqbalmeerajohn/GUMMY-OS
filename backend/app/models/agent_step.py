"""AgentStep model — one agent invocation inside a run (Phase 3, M1).

A run is a sequence of steps; each step records which agent ran, its typed
input/output payloads, status, and cost. ``user_id`` is denormalized so RLS
stays a cheap direct-column policy (the ``messages.user_id`` decision).
``UNIQUE(run_id, seq)`` is the deterministic ordering key. Mutable while the
step is in flight → ``TimestampMixin``. See PHASE3_PLAN.md §4.5/§12.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import StepStatus, enum_type

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun

_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in StepStatus)


class AgentStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One agent invocation (a step) within an orchestration run."""

    __tablename__ = "agent_steps"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # Monotonic per-run ordinal assigned at append (the messages.seq pattern).
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[StepStatus] = mapped_column(
        enum_type(StepStatus, "step_status"),
        nullable=False,
        default=StepStatus.RUNNING,
        server_default=text("'running'"),
    )
    input: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    output: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0"),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    run: Mapped[AgentRun] = relationship(back_populates="steps")

    __table_args__ = (
        Index("ix_agent_steps_run_id", "run_id"),
        Index("ix_agent_steps_user_id", "user_id"),
        UniqueConstraint(
            "run_id",
            "seq",
            name="uq_agent_steps_run_id_seq",
        ),
        CheckConstraint(
            f"status IN ({_STATUS_VALUES})",
            name="status_valid",
        ),
        CheckConstraint(
            "cost_tokens >= 0",
            name="cost_tokens_non_negative",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AgentStep id={self.id} run_id={self.run_id} "
            f"agent={self.agent_key} seq={self.seq} status={self.status}>"
        )
