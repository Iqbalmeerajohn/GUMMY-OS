"""MemoryEmbedding model — the vector representation of a memory's content.

The ``embedding_vector`` column is a pgvector ``vector`` on PostgreSQL (where ANN
search runs) and degrades to JSON on SQLite so the embedding/dedupe logic is
testable without Postgres.
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
    from app.models.memory import Memory


class MemoryEmbedding(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One embedding of a memory, per embedding model."""

    __tablename__ = "memory_embeddings"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memories.id", ondelete="CASCADE"),
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_vector: Mapped[list[float]] = mapped_column(
        Vector(EMBEDDING_DIMENSION).with_variant(JSON(), "sqlite"),
        nullable=False,
    )

    memory: Mapped[Memory] = relationship(back_populates="embeddings")

    __table_args__ = (
        UniqueConstraint(
            "memory_id",
            "embedding_model",
            name="uq_memory_embeddings_memory_id_embedding_model",
        ),
        Index("ix_memory_embeddings_memory_id", "memory_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<MemoryEmbedding id={self.id} memory_id={self.memory_id} "
            f"model={self.embedding_model!r} dim={self.embedding_dimension}>"
        )
