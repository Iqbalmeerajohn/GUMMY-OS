"""initial memory schema (users, memories, memory_versions)

Revision ID: 0001_initial_memory_schema
Revises:
Create Date: 2026-06-06

Day 2 of Phase 1 — the relational data layer for the Memory Engine. No pgvector,
embeddings, or retrieval here (those land on later days). This migration mirrors
the SQLAlchemy models and reuses the project enum types so the DDL stays identical
to ``Base.metadata`` (clean autogenerate diffs going forward).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.models.enums import (
    MemoryCategory,
    MemoryChangeReason,
    MemoryStatus,
    enum_type,
)

# revision identifiers, used by Alembic.
revision: str = "0001_initial_memory_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CATEGORY_VALUES = ", ".join(f"'{c.value}'" for c in MemoryCategory)
_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in MemoryStatus)
_CHANGE_REASON_VALUES = ", ".join(f"'{r.value}'" for r in MemoryChangeReason)


def upgrade() -> None:
    # gen_random_uuid() is built into Postgres 13+; pgcrypto guarantees it on
    # older managed instances. Harmless if already present.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "memories",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "category",
            enum_type(MemoryCategory, "memory_category"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "importance_score",
            sa.Float(),
            server_default=sa.text("0.5"),
            nullable=False,
        ),
        sa.Column(
            "confidence_score",
            sa.Float(),
            server_default=sa.text("0.5"),
            nullable=False,
        ),
        sa.Column(
            "status",
            enum_type(MemoryStatus, "memory_status"),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_memories"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_memories_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "importance_score >= 0 AND importance_score <= 1",
            name="importance_score_range",
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="confidence_score_range",
        ),
        sa.CheckConstraint(
            f"category IN ({_CATEGORY_VALUES})",
            name="category_valid",
        ),
        sa.CheckConstraint(
            f"status IN ({_STATUS_VALUES})",
            name="status_valid",
        ),
    )
    op.create_index("ix_memories_user_id", "memories", ["user_id"])
    op.create_index("ix_memories_user_id_category", "memories", ["user_id", "category"])
    op.create_index("ix_memories_user_id_status", "memories", ["user_id", "status"])

    op.create_table(
        "memory_versions",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("memory_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_snapshot", sa.Text(), nullable=False),
        sa.Column(
            "change_reason",
            enum_type(MemoryChangeReason, "memory_change_reason"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_versions"),
        sa.ForeignKeyConstraint(
            ["memory_id"],
            ["memories.id"],
            name="fk_memory_versions_memory_id_memories",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "memory_id",
            "version_number",
            name="uq_memory_versions_memory_id_version_number",
        ),
        sa.CheckConstraint(
            "version_number >= 1",
            name="version_number_positive",
        ),
        sa.CheckConstraint(
            f"change_reason IN ({_CHANGE_REASON_VALUES})",
            name="change_reason_valid",
        ),
    )
    op.create_index("ix_memory_versions_memory_id", "memory_versions", ["memory_id"])


def downgrade() -> None:
    # Dropping a table drops its indexes and constraints; reverse dependency order.
    op.drop_table("memory_versions")
    op.drop_table("memories")
    op.drop_table("users")
