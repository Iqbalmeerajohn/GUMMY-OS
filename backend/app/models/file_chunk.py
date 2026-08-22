"""FileChunk model — one deterministic slice of a file's extracted text (M6).

Chunks are the reusable substrate for future RAG: each row carries the chunk's
text, its ordinal position in the document (``chunk_index``), an approximate
``token_count``, and free-form ``metadata_json`` (page numbers, char offsets,
etc.). Chunking is deterministic (see
:mod:`app.services.files.chunking_service`) so the same file always yields the
same chunks — safe to re-derive embeddings from later without drift.

``goal_id``-style denormalized ``user_id`` carries the standard fail-closed
RLS policy without a join. The parent ``file_id`` is ``ON DELETE CASCADE``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import EMBEDDING_DIMENSION
from app.database.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.file import File


class FileChunk(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A tenant-scoped, ordered text chunk belonging to one file."""

    __tablename__ = "file_chunks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 0-based ordinal of this chunk within the document (stable, gap-free).
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    metadata_json: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )

    # The chunk's vector, on the row rather than in a side table: a chunk is
    # embedded once by the configured model and re-embedded wholesale on
    # re-index, so the per-model uniqueness that justifies a separate
    # memory_embeddings table buys nothing here — only a join on the
    # hottest read path. Nullable: a chunk exists before it is embedded,
    # and that gap is exactly what `indexed_at` reports.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION).with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    # Which model produced it, so a model change is detectable rather than
    # silently mixing incompatible vectors in one index.
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    file: Mapped[File] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_file_chunks_user_id", "user_id"),
        Index("ix_file_chunks_file_id", "file_id"),
        Index("ix_file_chunks_file_id_chunk_index", "file_id", "chunk_index"),
        CheckConstraint("chunk_index >= 0", name="chunk_index_non_negative"),
        CheckConstraint("token_count >= 0", name="token_count_non_negative"),
    )

    def __repr__(self) -> str:
        return (
            f"<FileChunk id={self.id} file_id={self.file_id} "
            f"index={self.chunk_index} tokens={self.token_count}>"
        )
