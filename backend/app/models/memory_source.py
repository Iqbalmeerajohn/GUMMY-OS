"""MemorySource model — provenance link from a memory to its origin (Phase 2).

The bridge that records *where Gummy learned a fact*. A memory may derive from a
conversation/message; the link uses ``ON DELETE SET NULL`` on the source so a
durable, user-owned memory survives deletion of the chat it came from (the link
just loses its back-pointer). ``source_kind`` grows as future agents/documents
become sources — the shared provenance seam for the agent workforce
(see PHASE2_PLAN.md §7).

No ORM relationship to ``memories`` is declared here so the Phase 1 ``Memory``
model stays untouched; the FK column is sufficient.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import SourceKind, enum_type

if TYPE_CHECKING:
    pass

_SOURCE_KIND_VALUES = ", ".join(f"'{k.value}'" for k in SourceKind)


class MemorySource(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A provenance record linking a memory to the source it was distilled from."""

    __tablename__ = "memory_sources"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    memory_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_kind: Mapped[SourceKind] = mapped_column(
        enum_type(SourceKind, "source_kind"),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_memory_sources_user_id", "user_id"),
        Index("ix_memory_sources_memory_id", "memory_id"),
        Index("ix_memory_sources_conversation_id", "conversation_id"),
        CheckConstraint(
            f"source_kind IN ({_SOURCE_KIND_VALUES})",
            name="source_kind_valid",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<MemorySource id={self.id} memory_id={self.memory_id} "
            f"kind={self.source_kind}>"
        )
