"""add messages.seq monotonic ordinal (Phase 2, M2)

Revision ID: 0010_add_message_seq
Revises: 0009_add_memory_sources
Create Date: 2026-06-08

Deterministic, insertion-faithful message ordering. ``created_at`` is fixed per
Postgres transaction (and second-resolution on SQLite), so it collides for
messages appended together; the random uuid PK is no tiebreak. ``seq`` is a
per-conversation ordinal assigned at append, with a UNIQUE(conversation_id, seq)
constraint for integrity. The column is added NOT NULL directly: ``messages`` is
created in 0007 and carries no rows until the app writes (post-M3), so no backfill
is required. See PHASE2_PLAN.md §4.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_add_message_seq"
down_revision: str | None = "0009_add_memory_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("seq", sa.BigInteger(), nullable=False))
    op.create_unique_constraint(
        "uq_messages_conversation_id_seq",
        "messages",
        ["conversation_id", "seq"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_messages_conversation_id_seq", "messages", type_="unique"
    )
    op.drop_column("messages", "seq")
