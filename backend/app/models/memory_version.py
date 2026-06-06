"""MemoryVersion model — an append-only history snapshot of a memory."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import MemoryChangeReason, enum_type

if TYPE_CHECKING:
    from app.models.memory import Memory

_CHANGE_REASON_VALUES = ", ".join(f"'{r.value}'" for r in MemoryChangeReason)


class MemoryVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An immutable snapshot of a memory's content at a point in time."""

    __tablename__ = "memory_versions"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    change_reason: Mapped[MemoryChangeReason] = mapped_column(
        enum_type(MemoryChangeReason, "memory_change_reason"),
        nullable=False,
    )

    memory: Mapped[Memory] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint(
            "memory_id",
            "version_number",
            name="uq_memory_versions_memory_id_version_number",
        ),
        Index("ix_memory_versions_memory_id", "memory_id"),
        CheckConstraint(
            "version_number >= 1",
            name="version_number_positive",
        ),
        CheckConstraint(
            f"change_reason IN ({_CHANGE_REASON_VALUES})",
            name="change_reason_valid",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<MemoryVersion id={self.id} memory_id={self.memory_id} "
            f"v={self.version_number} reason={self.change_reason}>"
        )
