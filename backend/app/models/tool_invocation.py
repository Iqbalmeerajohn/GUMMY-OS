"""ToolInvocation model — the audit row for every tool call (Phase 3, M6).

Append-only: one row per attempted tool call, whatever the gate decided —
allowed (Green, executed), pending (Yellow/Red prompt path or executor
deferred), or blocked (manifest/ceiling violation). ``user_id`` is
denormalized for direct-column RLS. See PHASE3_PLAN.md §10.
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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    PermissionTier,
    ToolDecision,
    ToolRunStatus,
    enum_type,
)

if TYPE_CHECKING:
    pass

_TIER_VALUES = ", ".join(f"'{t.value}'" for t in PermissionTier)
_DECISION_VALUES = ", ".join(f"'{d.value}'" for d in ToolDecision)
_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in ToolRunStatus)


class ToolInvocation(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One audited tool call: args, tier, gate decision, outcome, cost."""

    __tablename__ = "tool_invocations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_key: Mapped[str] = mapped_column(String(64), nullable=False)
    args: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    tier: Mapped[PermissionTier] = mapped_column(
        enum_type(PermissionTier, "tool_tier"),
        nullable=False,
    )
    decision: Mapped[ToolDecision] = mapped_column(
        enum_type(ToolDecision, "tool_decision"),
        nullable=False,
    )
    status: Mapped[ToolRunStatus] = mapped_column(
        enum_type(ToolRunStatus, "tool_run_status"),
        nullable=False,
    )
    # Why the gate decided what it decided (audit trail).
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Compact result reference/preview (full outputs are not persisted here).
    output_ref: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_tool_invocations_user_id", "user_id"),
        Index("ix_tool_invocations_run_id", "run_id"),
        CheckConstraint(
            f"tier IN ({_TIER_VALUES})",
            name="tier_valid",
        ),
        CheckConstraint(
            f"decision IN ({_DECISION_VALUES})",
            name="decision_valid",
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
            f"<ToolInvocation id={self.id} tool={self.tool_key} "
            f"tier={self.tier} decision={self.decision} status={self.status}>"
        )
