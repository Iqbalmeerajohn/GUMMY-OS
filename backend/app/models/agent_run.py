"""AgentRun model — one orchestration trace per turn/job (Phase 3, M1).

Every orchestration (a chat turn routed through the agent framework, or a
future scheduler job) writes exactly one run row plus child ``agent_steps``.
``conversation_id`` uses ``ON DELETE SET NULL`` so the audit/cost trail
survives thread deletion. Mutable (status/cost updates) → ``TimestampMixin``.
See PHASE3_PLAN.md §4.5/§12.
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
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import RunStatus, RunTrigger, enum_type

if TYPE_CHECKING:
    from app.models.agent_message import AgentMessage
    from app.models.agent_step import AgentStep

_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in RunStatus)
_TRIGGER_VALUES = ", ".join(f"'{t.value}'" for t in RunTrigger)


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single traced, costed orchestration."""

    __tablename__ = "agent_runs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    trigger: Mapped[RunTrigger] = mapped_column(
        enum_type(RunTrigger, "run_trigger"),
        nullable=False,
        default=RunTrigger.CHAT,
        server_default=text("'chat'"),
    )
    # The Router's chosen shape + steps + rationale (observability / evals).
    route_plan: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    status: Mapped[RunStatus] = mapped_column(
        enum_type(RunStatus, "run_status"),
        nullable=False,
        default=RunStatus.RUNNING,
        server_default=text("'running'"),
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

    steps: Mapped[list[AgentStep]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AgentStep.seq",
    )
    messages: Mapped[list[AgentMessage]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AgentMessage.seq",
    )

    __table_args__ = (
        Index("ix_agent_runs_user_id", "user_id"),
        Index("ix_agent_runs_conversation_id", "conversation_id"),
        Index("ix_agent_runs_user_id_created_at", "user_id", "created_at"),
        CheckConstraint(
            f"status IN ({_STATUS_VALUES})",
            name="status_valid",
        ),
        CheckConstraint(
            f"trigger IN ({_TRIGGER_VALUES})",
            name="trigger_valid",
        ),
        CheckConstraint(
            "cost_tokens >= 0",
            name="cost_tokens_non_negative",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AgentRun id={self.id} user_id={self.user_id} "
            f"status={self.status} trigger={self.trigger}>"
        )
