"""add memory_sources provenance table (Phase 2, M1)

Revision ID: 0009_add_memory_sources
Revises: 0008_add_conversation_summaries
Create Date: 2026-06-08

The conversation -> memory provenance link. ON DELETE SET NULL on the source
(conversation/message) keeps a durable, user-owned memory alive after its source
chat is deleted; ON DELETE CASCADE on the memory removes the link when the memory
is purged. RLS fail-closed on ``user_id``. See docs/PHASE2_PLAN.md §7/§9.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.models.enums import SourceKind, enum_type

# revision identifiers, used by Alembic.
revision: str = "0009_add_memory_sources"
down_revision: str | None = "0008_add_conversation_summaries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

_SOURCE_KIND_VALUES = ", ".join(f"'{k.value}'" for k in SourceKind)


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
        "memory_sources",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("memory_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column(
            "source_kind",
            enum_type(SourceKind, "source_kind"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_sources"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_memory_sources_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["memory_id"],
            ["memories.id"],
            name="fk_memory_sources_memory_id_memories",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_memory_sources_conversation_id_conversations",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name="fk_memory_sources_message_id_messages",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            f"source_kind IN ({_SOURCE_KIND_VALUES})",
            name="source_kind_valid",
        ),
    )
    op.create_index(
        "ix_memory_sources_user_id", "memory_sources", ["user_id"]
    )
    op.create_index(
        "ix_memory_sources_memory_id", "memory_sources", ["memory_id"]
    )
    op.create_index(
        "ix_memory_sources_conversation_id",
        "memory_sources",
        ["conversation_id"],
    )

    # RLS: direct-column tenant isolation (fail-closed).
    op.execute("ALTER TABLE memory_sources ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY memory_sources_tenant_isolation ON memory_sources "
        f"FOR ALL USING (user_id = {_GUC}) "
        f"WITH CHECK (user_id = {_GUC})"
    )
    _grant_app_role("memory_sources")


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS memory_sources_tenant_isolation ON memory_sources"
    )
    op.execute("ALTER TABLE memory_sources DISABLE ROW LEVEL SECURITY")
    op.drop_table("memory_sources")
