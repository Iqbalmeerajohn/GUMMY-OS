"""Conversation model — a persistent chat thread (Phase 2).

A conversation is a tenant-scoped thread of ``messages`` with a rolling/closing
summary history (``conversation_summaries``). Relational columns only; the turn,
summary, and extraction logic live in the service layer (see PHASE2_PLAN.md §3).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
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
    ConversationStatus,
    enum_type,
)

if TYPE_CHECKING:
    from app.models.conversation_summary import ConversationSummary
    from app.models.message import Message

_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in ConversationStatus)
_AGENT_CONTEXT_VALUES = ", ".join(f"'{a.value}'" for a in AgentContext)


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single chat thread belonging to a user."""

    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # NULL until the title is generated (async backfill — PHASE2_PLAN.md §21 Q1).
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ConversationStatus] = mapped_column(
        enum_type(ConversationStatus, "conversation_status"),
        nullable=False,
        default=ConversationStatus.ACTIVE,
        server_default=text("'active'"),
    )
    # Forward seam for the Agent Framework; every thread has a hub, default general.
    agent_context: Mapped[AgentContext] = mapped_column(
        enum_type(AgentContext, "agent_context"),
        nullable=False,
        default=AgentContext.GENERAL,
        server_default=text("'general'"),
    )
    pinned: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at",
    )
    summaries: Mapped[list[ConversationSummary]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ConversationSummary.version_number",
    )

    __table_args__ = (
        Index("ix_conversations_user_id", "user_id"),
        Index("ix_conversations_user_id_status", "user_id", "status"),
        Index(
            "ix_conversations_user_id_last_message_at",
            "user_id",
            "last_message_at",
        ),
        Index("ix_conversations_user_id_deleted_at", "user_id", "deleted_at"),
        CheckConstraint(
            f"status IN ({_STATUS_VALUES})",
            name="status_valid",
        ),
        CheckConstraint(
            f"agent_context IN ({_AGENT_CONTEXT_VALUES})",
            name="agent_context_valid",
        ),
        CheckConstraint(
            "message_count >= 0",
            name="message_count_non_negative",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Conversation id={self.id} user_id={self.user_id} "
            f"status={self.status} messages={self.message_count}>"
        )
