"""add files + file_chunks tables (M6 Files System)

Revision ID: 0021_add_files
Revises: 0020_add_goal_milestones
Create Date: 2026-06-24

The files knowledge layer: ``files`` records an uploaded document with two
independent lifecycles (``upload_status`` for the bytes, ``processing_status``
for the extraction), and ``file_chunks`` holds the deterministic, RAG-ready
text slices. ``file_chunks.file_id`` is ``ON DELETE CASCADE`` (chunks have no
life without their file). Both tables: denormalized ``user_id``, fail-closed
direct-column RLS, conditional ``gummy_app`` grant — the standard pattern.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.enums import ProcessingStatus, UploadStatus

# revision identifiers, used by Alembic.
revision: str = "0021_add_files"
down_revision: str | None = "0020_add_goal_milestones"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

_UPLOAD_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in UploadStatus)
_PROCESSING_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in ProcessingStatus)


def _grant_app_role(table: str) -> None:
    """Grant CRUD on ``table`` to the non-bypass ``gummy_app`` role if it exists."""
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gummy_app') THEN "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gummy_app; "
        "END IF; END $$;"
    )


def _enable_rls(table: str) -> None:
    """Enable RLS with the standard fail-closed tenant policy."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON {table} "
        f"FOR ALL USING (user_id = {_GUC}) "
        f"WITH CHECK (user_id = {_GUC})"
    )


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column(
            "upload_status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "processing_status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "chunk_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_files"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_files_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"upload_status IN ({_UPLOAD_STATUS_VALUES})",
            name="upload_status_valid",
        ),
        sa.CheckConstraint(
            f"processing_status IN ({_PROCESSING_STATUS_VALUES})",
            name="processing_status_valid",
        ),
        sa.CheckConstraint("size_bytes >= 0", name="size_bytes_non_negative"),
        sa.CheckConstraint("chunk_count >= 0", name="chunk_count_non_negative"),
    )
    op.create_index("ix_files_user_id", "files", ["user_id"])
    op.create_index("ix_files_user_id_created_at", "files", ["user_id", "created_at"])
    _enable_rls("files")
    _grant_app_role("files")

    op.create_table(
        "file_chunks",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "token_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_file_chunks"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_file_chunks_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name="fk_file_chunks_file_id_files",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("chunk_index >= 0", name="chunk_index_non_negative"),
        sa.CheckConstraint("token_count >= 0", name="token_count_non_negative"),
    )
    op.create_index("ix_file_chunks_user_id", "file_chunks", ["user_id"])
    op.create_index("ix_file_chunks_file_id", "file_chunks", ["file_id"])
    op.create_index(
        "ix_file_chunks_file_id_chunk_index",
        "file_chunks",
        ["file_id", "chunk_index"],
    )
    _enable_rls("file_chunks")
    _grant_app_role("file_chunks")


def downgrade() -> None:
    for table in ("file_chunks", "files"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("file_chunks")
    op.drop_table("files")
