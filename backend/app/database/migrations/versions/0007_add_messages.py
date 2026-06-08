"""add messages table (Phase 2, M1)

Revision ID: 0007_add_messages
Revises: 0006_add_conversations
Create Date: 2026-06-08

Append-only message turns. ``user_id`` is denormalized so RLS uses a cheap
direct-column policy on this highest-volume table (no parent subquery), matching
0005's ``memory_embeddings`` decision. A GIN full-text index over ``content``
backs keyword conversation search. See docs/PHASE2_PLAN.md §4/§9.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.enums import MessageRole, enum_type

# revision identifiers, used by Alembic.
revision: str = "0007_add_messages"
down_revision: str | None = "0006_add_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

_ROLE_VALUES = ", ".join(f"'{r.value}'" for r in MessageRole)


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
        "messages",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            enum_type(MessageRole, "message_role"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_messages_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"role IN ({_ROLE_VALUES})",
            name="role_valid",
        ),
    )
    op.create_index(
        "ix_messages_conversation_id_created_at",
        "messages",
        ["conversation_id", "created_at"],
    )
    op.create_index("ix_messages_user_id", "messages", ["user_id"])
    # Keyword search over message content (Postgres full-text).
    op.execute(
        "CREATE INDEX ix_messages_content_fts ON messages "
        "USING gin (to_tsvector('english', content))"
    )

    # RLS: direct-column tenant isolation (fail-closed).
    op.execute("ALTER TABLE messages ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY messages_tenant_isolation ON messages "
        f"FOR ALL USING (user_id = {_GUC}) "
        f"WITH CHECK (user_id = {_GUC})"
    )
    _grant_app_role("messages")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS messages_tenant_isolation ON messages")
    op.execute("ALTER TABLE messages DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS ix_messages_content_fts")
    op.drop_table("messages")
