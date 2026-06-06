"""add recall tracking to memories

Revision ID: 0004_add_memory_recall_tracking
Revises: 0003_add_memory_embeddings
Create Date: 2026-06-07

Day 5 of Phase 1 — adds the fields the hybrid retrieval engine reinforces:
``recall_count`` (how often a memory was retrieved) and ``last_recalled_at``
(for recency scoring + reinforcement cooldown), plus a supporting index.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_add_memory_recall_tracking"
down_revision: str | None = "0003_add_memory_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memories",
        sa.Column(
            "recall_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "memories",
        sa.Column("last_recalled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_memories_user_id_last_recalled_at",
        "memories",
        ["user_id", "last_recalled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_memories_user_id_last_recalled_at", table_name="memories")
    op.drop_column("memories", "last_recalled_at")
    op.drop_column("memories", "recall_count")
