"""ConversationSummaryEmbedding model — vector for a conversation summary.

A direct mirror of ``memory_embeddings``: the ``embedding_vector`` is a pgvector
``vector`` on PostgreSQL and degrades to JSON on SQLite so the suite stays
Postgres-free. Powers semantic conversation search over summaries, not raw
messages (see PHASE2_PLAN.md §5).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import EMBEDDING_DIMENSION
from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.conversation_summary import ConversationSummary


class ConversationSummaryEmbedding(
    UUIDPrimaryKeyMixin, CreatedAtMixin, Base
):
    """One embedding of a conversation summary, per embedding model."""

    __tablename__ = "conversation_summary_embeddings"

    summary_id: Mapped[uuid.UUID] = mapped_column(
        # Explicit short name: the convention-generated name would exceed
        # Postgres's 63-char identifier limit.
        ForeignKey(
            "conversation_summaries.id",
            ondelete="CASCADE",
            name="fk_conv_summary_embeddings_summary_id",
        ),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_vector: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSION).with_variant(JSON(), "sqlite"),
        nullable=False,
    )

    summary: Mapped[ConversationSummary] = relationship(
        back_populates="embedding"
    )

    __table_args__ = (
        UniqueConstraint(
            "summary_id",
            "embedding_model",
            name="uq_conversation_summary_embeddings_summary_id_embedding_model",
        ),
        Index(
            "ix_conversation_summary_embeddings_summary_id",
            "summary_id",
        ),
        Index(
            "ix_conversation_summary_embeddings_user_id",
            "user_id",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ConversationSummaryEmbedding id={self.id} "
            f"summary_id={self.summary_id} model={self.embedding_model!r}>"
        )
