"""add conversations.last_extracted_seq (Phase 2, M6)

Revision ID: 0011_extraction_watermark
Revises: 0010_add_message_seq
Create Date: 2026-06-08

The memory-extraction watermark: messages with ``seq <= last_extracted_seq`` have
already been processed, so the conversation→memory consumer never re-extracts (and
re-saves) the same facts. Added NOT NULL with a server default of 0; the table is
empty until the app writes, and existing rows default to 0 (whole thread is the
delta). RLS + ``gummy_app`` grants are table-level (0006), so a new column is
covered automatically. See PHASE2_PLAN.md §6.

NOTE: the revision id is kept short — Alembic's ``alembic_version.version_num`` is
VARCHAR(32), so ids longer than that fail to record on Postgres.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_extraction_watermark"
down_revision: str | None = "0010_add_message_seq"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "last_extracted_seq",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "last_extracted_seq")
