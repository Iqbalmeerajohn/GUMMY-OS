"""ActionApproval model — the human-in-the-loop seam (Phase 3, M10).

One row per Yellow/Red action the Policy gate routed to "prompt": a preview
of what would happen, awaiting the user's decision. Append-only decision
trail (security-system §7): status moves pending → approved/rejected/expired
exactly once; **approving records the decision only — no executor exists in
Phase 3**, so no external side effect can fire.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ApprovalStatus, PermissionTier, enum_type

_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in ApprovalStatus)
_TIER_VALUES = ", ".join(f"'{t.value}'" for t in PermissionTier)


class ActionApproval(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A pending/decided approval for one proposed Yellow/Red action."""

    __tablename__ = "action_approvals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The producing run; SET NULL so the decision trail survives run cleanup.
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_key: Mapped[str] = mapped_column(String(64), nullable=False)
    # What kind of action (the tool key for tool-driven approvals).
    action_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    tier: Mapped[PermissionTier] = mapped_column(
        enum_type(PermissionTier, "approval_tier"),
        nullable=False,
    )
    # Human-readable preview of exactly what would happen if approved.
    preview: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        enum_type(ApprovalStatus, "approval_status"),
        nullable=False,
        default=ApprovalStatus.PENDING,
        server_default="pending",
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_action_approvals_user_id", "user_id"),
        Index("ix_action_approvals_user_id_status", "user_id", "status"),
        Index("ix_action_approvals_run_id", "run_id"),
        CheckConstraint(
            f"status IN ({_STATUS_VALUES})",
            name="status_valid",
        ),
        CheckConstraint(
            f"tier IN ({_TIER_VALUES})",
            name="tier_valid",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ActionApproval id={self.id} kind={self.action_kind} "
            f"tier={self.tier} status={self.status}>"
        )
