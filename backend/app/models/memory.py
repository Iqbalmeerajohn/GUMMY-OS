"""Memory model — the semantic long-term store (relational columns only).

Embeddings live in a separate table introduced in a later day; this model owns the
structured, queryable fields and the lifecycle status.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import MemoryCategory, MemoryStatus, enum_type

if TYPE_CHECKING:
    from app.models.memory_version import MemoryVersion
    from app.models.user import User

# Allowed enum values, kept beside the model for the DB CHECK constraints.
_CATEGORY_VALUES = ", ".join(f"'{c.value}'" for c in MemoryCategory)
_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in MemoryStatus)


class Memory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single durable memory belonging to a user."""

    __tablename__ = "memories"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[MemoryCategory] = mapped_column(
        enum_type(MemoryCategory, "memory_category"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("0.5"),
    )
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("0.5"),
    )
    status: Mapped[MemoryStatus] = mapped_column(
        enum_type(MemoryStatus, "memory_status"),
        nullable=False,
        default=MemoryStatus.ACTIVE,
        server_default=text("'active'"),
    )

    user: Mapped[User] = relationship(back_populates="memories")
    versions: Mapped[list[MemoryVersion]] = relationship(
        back_populates="memory",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MemoryVersion.version_number",
    )

    __table_args__ = (
        Index("ix_memories_user_id", "user_id"),
        Index("ix_memories_user_id_category", "user_id", "category"),
        Index("ix_memories_user_id_status", "user_id", "status"),
        CheckConstraint(
            "importance_score >= 0 AND importance_score <= 1",
            name="importance_score_range",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="confidence_score_range",
        ),
        CheckConstraint(
            f"category IN ({_CATEGORY_VALUES})",
            name="category_valid",
        ),
        CheckConstraint(
            f"status IN ({_STATUS_VALUES})",
            name="status_valid",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Memory id={self.id} user_id={self.user_id} "
            f"category={self.category} status={self.status}>"
        )
