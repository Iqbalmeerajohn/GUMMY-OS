"""ConversationSummary model — versioned rolling/closing summaries (Phase 2).

Append-only history (``CreatedAtMixin``). Each summary records a watermark
(``covers_through_message_id``) so the next refresh summarizes only the delta.
The embedded vector lives in a sibling table, mirroring ``memory_embeddings``
(see PHASE2_PLAN.md §5).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import SummaryType, enum_type

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.conversation_summary_embedding import (
        ConversationSummaryEmbedding,
    )

_SUMMARY_TYPE_VALUES = ", ".join(f"'{t.value}'" for t in SummaryType)


class ConversationSummary(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A distilled summary of a conversation up to a watermark message."""

    __tablename__ = "conversation_summaries"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    summary_type: Mapped[SummaryType] = mapped_column(
        enum_type(SummaryType, "summary_type"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Watermark: this summary reflects the thread up to (and including) this
    # message. SET NULL on message delete keeps the summary; it just loses the
    # back-pointer (the summary text is durable).
    covers_through_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    conversation: Mapped[Conversation] = relationship(back_populates="summaries")
    embedding: Mapped[ConversationSummaryEmbedding | None] = relationship(
        back_populates="summary",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "version_number",
            name="uq_conversation_summaries_conversation_id_version_number",
        ),
        Index(
            "ix_conversation_summaries_conversation_id",
            "conversation_id",
        ),
        Index("ix_conversation_summaries_user_id", "user_id"),
        CheckConstraint(
            "version_number >= 1",
            name="version_number_positive",
        ),
        CheckConstraint(
            f"summary_type IN ({_SUMMARY_TYPE_VALUES})",
            name="summary_type_valid",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ConversationSummary id={self.id} "
            f"conversation_id={self.conversation_id} "
            f"type={self.summary_type} v={self.version_number}>"
        )
