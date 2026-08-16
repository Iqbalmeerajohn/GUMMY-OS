"""File model — a user-uploaded document in the knowledge system (M6).

A file is the durable record of something the user uploaded into GUMMY OS: its
identity (``filename`` / ``original_filename``), its bytes' provenance
(``mime_type`` / ``size_bytes`` / ``storage_path``), and two independent
lifecycles — the *upload* of the bytes (:class:`~app.models.enums.UploadStatus`)
and the *processing* into chunks (:class:`~app.models.enums.ProcessingStatus`).

Processed text lives in child :class:`~app.models.file_chunk.FileChunk` rows
(deterministic, reusable by future RAG). ``user_id`` is the tenant key carrying
the standard fail-closed, direct-column RLS policy.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ProcessingStatus, UploadStatus, enum_type
from app.models.file_chunk import FileChunk

_UPLOAD_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in UploadStatus)
_PROCESSING_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in ProcessingStatus)

# Stored MIME type bound (also validated at the schema edge).
FILE_MIME_TYPE_MAX_LENGTH = 128
FILE_NAME_MAX_LENGTH = 512


class File(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant-scoped uploaded file with its processing lifecycle."""

    __tablename__ = "files"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # ``filename`` is the (possibly sanitized) name we store under; the
    # ``original_filename`` preserves exactly what the user uploaded.
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(
        String(FILE_MIME_TYPE_MAX_LENGTH), nullable=False
    )
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Opaque storage key resolved by the storage backend (local path today,
    # an object key under R2 / S3 tomorrow). Nullable until
    # the bytes are persisted.
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_status: Mapped[UploadStatus] = mapped_column(
        enum_type(UploadStatus, "file_upload_status"),
        nullable=False,
        default=UploadStatus.PENDING,
        server_default=text("'pending'"),
    )
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        enum_type(ProcessingStatus, "file_processing_status"),
        nullable=False,
        default=ProcessingStatus.PENDING,
        server_default=text("'pending'"),
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    # Set when processing_status == failed, for surfacing/observability.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    chunks: Mapped[list[FileChunk]] = relationship(
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="FileChunk.chunk_index",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_files_user_id", "user_id"),
        Index("ix_files_user_id_created_at", "user_id", "created_at"),
        CheckConstraint(
            f"upload_status IN ({_UPLOAD_STATUS_VALUES})",
            name="upload_status_valid",
        ),
        CheckConstraint(
            f"processing_status IN ({_PROCESSING_STATUS_VALUES})",
            name="processing_status_valid",
        ),
        CheckConstraint("size_bytes >= 0", name="size_bytes_non_negative"),
        CheckConstraint("chunk_count >= 0", name="chunk_count_non_negative"),
    )

    def __repr__(self) -> str:
        return (
            f"<File id={self.id} user_id={self.user_id} "
            f"processing={self.processing_status} "
            f"name={self.original_filename[:30]!r}>"
        )
