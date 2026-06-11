"""AgentMessage model — the inter-agent audit trail (Phase 3, M1).

Every orchestrator-mediated hop (task hand-off, result, error) is persisted as
one append-only row so multi-agent runs are fully traceable. ``to_agent`` is
NULL when the counterparty is the Orchestrator itself. Append-only →
``CreatedAtMixin``. See PHASE3_PLAN.md §9.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import AgentMessageRole, enum_type

if TYPE_CHECKING:
    from app.models.agent_run import AgentRun

_ROLE_VALUES = ", ".join(f"'{r.value}'" for r in AgentMessageRole)


class AgentMessage(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One audited inter-agent hop within an orchestration run."""

    __tablename__ = "agent_messages"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_agent: Mapped[str] = mapped_column(String(64), nullable=False)
    # NULL = the Orchestrator is the recipient.
    to_agent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[AgentMessageRole] = mapped_column(
        enum_type(AgentMessageRole, "agent_message_role"),
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    # Monotonic per-run ordinal assigned at append (the messages.seq pattern).
    seq: Mapped[int] = mapped_column(Integer, nullable=False)

    run: Mapped[AgentRun] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_agent_messages_run_id", "run_id"),
        Index("ix_agent_messages_user_id", "user_id"),
        UniqueConstraint(
            "run_id",
            "seq",
            name="uq_agent_messages_run_id_seq",
        ),
        CheckConstraint(
            f"role IN ({_ROLE_VALUES})",
            name="role_valid",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AgentMessage id={self.id} run_id={self.run_id} "
            f"from={self.from_agent} to={self.to_agent} seq={self.seq}>"
        )
