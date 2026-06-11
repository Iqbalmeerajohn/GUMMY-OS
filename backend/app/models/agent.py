"""Agent model — the registry catalog of available agents (Phase 3, M1).

One row per agent the framework can dispatch to. Built-in (global) agents have
``user_id IS NULL`` and are seeded from in-code manifests at startup (M3);
``user_id`` is reserved for user-defined agents in a later phase. The manifest
fields mirror ``app/schemas/agents.AgentManifest`` — code is the source of
truth, the row carries runtime state (``enabled``) and is what RLS exposes to
tenants read-only (see PHASE3_PLAN.md §5).
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PermissionTier, enum_type

_CEILING_VALUES = ", ".join(f"'{t.value}'" for t in PermissionTier)


class Agent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A registry catalog row describing one dispatchable agent."""

    __tablename__ = "agents"

    # NULL = built-in (global) agent, visible to every tenant read-only.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    mission: Mapped[str] = mapped_column(Text, nullable=False)
    # Permission ceiling: the agent may never propose above this tier.
    ceiling: Mapped[PermissionTier] = mapped_column(
        enum_type(PermissionTier, "permission_tier"),
        nullable=False,
        default=PermissionTier.GREEN,
        server_default=text("'green'"),
    )
    # Allowed tool keys (JSON array of strings) — the tool manifest.
    tool_manifest: Mapped[list] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
        server_default=text("'[]'"),
    )
    # Model-tier hint for the runtime (e.g. "fast" | "default"). Free-form.
    model_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    __table_args__ = (
        Index("ix_agents_user_id", "user_id"),
        # One global namespace of agent keys (user-defined agents are a later
        # phase; revisit scoping then — additive change).
        UniqueConstraint("key", name="uq_agents_key"),
        CheckConstraint(
            f"ceiling IN ({_CEILING_VALUES})",
            name="ceiling_valid",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Agent id={self.id} key={self.key} ceiling={self.ceiling} "
            f"enabled={self.enabled}>"
        )
