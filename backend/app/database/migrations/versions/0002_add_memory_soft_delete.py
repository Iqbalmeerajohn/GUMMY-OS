"""add soft-delete to memories

Revision ID: 0002_add_memory_soft_delete
Revises: 0001_initial_memory_schema
Create Date: 2026-06-06

Day 3 of Phase 1 — adds the ``deleted_at`` column that backs soft deletes in the
Memory CRUD layer, plus an index to keep "active (not deleted)" filters fast.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_memory_soft_delete"
down_revision: str | None = "0001_initial_memory_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memories",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_memories_user_id_deleted_at",
        "memories",
        ["user_id", "deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_memories_user_id_deleted_at", table_name="memories")
    op.drop_column("memories", "deleted_at")
