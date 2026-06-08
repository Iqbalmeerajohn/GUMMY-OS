"""add conversation_summaries + summary embeddings (Phase 2, M1)

Revision ID: 0008_add_conversation_summaries
Revises: 0007_add_messages
Create Date: 2026-06-08

Versioned rolling/closing summaries plus their pgvector embeddings (mirroring
``memory_embeddings`` with an HNSW cosine index). The summary watermark FK to
``messages`` uses ON DELETE SET NULL so a summary survives message deletion. RLS
fail-closed on both tables. See docs/PHASE2_PLAN.md §5/§9.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from app.core.constants import EMBEDDING_DIMENSION
from app.models.enums import SummaryType, enum_type

# revision identifiers, used by Alembic.
revision: str = "0008_add_conversation_summaries"
down_revision: str | None = "0007_add_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

_SUMMARY_TYPE_VALUES = ", ".join(f"'{t.value}'" for t in SummaryType)


def _grant_app_role(table: str) -> None:
    """Grant CRUD on ``table`` to the non-bypass ``gummy_app`` role if it exists."""
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gummy_app') THEN "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gummy_app; "
        "END IF; END $$;"
    )


def upgrade() -> None:
    op.create_table(
        "conversation_summaries",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "summary_type",
            enum_type(SummaryType, "summary_type"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "covers_through_message_id", sa.Uuid(), nullable=True
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_summaries"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_conversation_summaries_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_conversation_summaries_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["covers_through_message_id"],
            ["messages.id"],
            name="fk_conversation_summaries_covers_through_message_id_messages",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "version_number",
            name="uq_conversation_summaries_conversation_id_version_number",
        ),
        sa.CheckConstraint(
            "version_number >= 1",
            name="version_number_positive",
        ),
        sa.CheckConstraint(
            f"summary_type IN ({_SUMMARY_TYPE_VALUES})",
            name="summary_type_valid",
        ),
    )
    op.create_index(
        "ix_conversation_summaries_conversation_id",
        "conversation_summaries",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_summaries_user_id",
        "conversation_summaries",
        ["user_id"],
    )

    op.create_table(
        "conversation_summary_embeddings",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("summary_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "embedding_vector", Vector(EMBEDDING_DIMENSION), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "id", name="pk_conversation_summary_embeddings"
        ),
        sa.ForeignKeyConstraint(
            ["summary_id"],
            ["conversation_summaries.id"],
            # Short name: the convention name would exceed PG's 63-char limit.
            name="fk_conv_summary_embeddings_summary_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_conversation_summary_embeddings_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "summary_id",
            "embedding_model",
            name="uq_conversation_summary_embeddings_summary_id_embedding_model",
        ),
    )
    op.create_index(
        "ix_conversation_summary_embeddings_summary_id",
        "conversation_summary_embeddings",
        ["summary_id"],
    )
    op.create_index(
        "ix_conversation_summary_embeddings_user_id",
        "conversation_summary_embeddings",
        ["user_id"],
    )
    # ANN index for cosine similarity over summary embeddings.
    op.execute(
        "CREATE INDEX ix_conversation_summary_embeddings_vector "
        "ON conversation_summary_embeddings "
        "USING hnsw (embedding_vector vector_cosine_ops)"
    )

    # RLS: direct-column tenant isolation on both tables (fail-closed).
    for table in ("conversation_summaries", "conversation_summary_embeddings"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"FOR ALL USING (user_id = {_GUC}) "
            f"WITH CHECK (user_id = {_GUC})"
        )
        _grant_app_role(table)


def downgrade() -> None:
    for table in ("conversation_summary_embeddings", "conversation_summaries"):
        op.execute(
            f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"
        )
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute(
        "DROP INDEX IF EXISTS ix_conversation_summary_embeddings_vector"
    )
    op.drop_table("conversation_summary_embeddings")
    op.drop_table("conversation_summaries")
