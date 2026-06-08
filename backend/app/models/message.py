"""Message model — one append-only turn in a conversation (Phase 2).

Immutable (``CreatedAtMixin``, no ``updated_at``). Carries a denormalized
``user_id`` so RLS uses a cheap direct-column policy on the highest-volume table
(matching the ``memory_embeddings.user_id`` decision in 0005; PHASE2_PLAN.md §4/§9).
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
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import MessageRole, enum_type

if TYPE_CHECKING:
    from app.models.conversation import Conversation

_ROLE_VALUES = ", ".join(f"'{r.value}'" for r in MessageRole)


class Message(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A single message turn (user / assistant / system / tool)."""

    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[MessageRole] = mapped_column(
        enum_type(MessageRole, "message_role"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Assistant-row provenance / cost accounting (NULL for user/system rows).
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Extensible bag: tool-call ids, citations, agent id (Agent Framework seam).
    # Attribute renamed to avoid the reserved declarative ``metadata`` name.
    extra_metadata: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (
        Index(
            "ix_messages_conversation_id_created_at",
            "conversation_id",
            "created_at",
        ),
        Index("ix_messages_user_id", "user_id"),
        CheckConstraint(
            f"role IN ({_ROLE_VALUES})",
            name="role_valid",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Message id={self.id} conversation_id={self.conversation_id} "
            f"role={self.role}>"
        )
