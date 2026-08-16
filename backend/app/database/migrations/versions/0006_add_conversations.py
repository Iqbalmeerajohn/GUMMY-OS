"""add conversations table (Phase 2, M1)

Revision ID: 0006_add_conversations
Revises: 0005_enable_rls
Create Date: 2026-06-08

Phase 2 Conversation System — the thread root. RLS is enabled in this same
migration (no window where the table is unprotected), using the identical
fail-closed GUC policy as 0005: an unset ``app.current_user_id`` resolves to NULL
and hides every row. See docs/PHASE2_PLAN.md §3/§9.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.models.enums import AgentContext, ConversationStatus, enum_type

# revision identifiers, used by Alembic.
revision: str = "0006_add_conversations"
down_revision: str | None = "0005_enable_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in ConversationStatus)
_AGENT_CONTEXT_VALUES = ", ".join(f"'{a.value}'" for a in AgentContext)


def _grant_app_role(table: str) -> None:
    """Grant CRUD on ``table`` to the non-bypass ``gummy_app`` role if it exists.

    Conditional so a fresh environment (role provisioned out-of-band, possibly
    after this migration) still applies cleanly.
    """
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gummy_app') THEN "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gummy_app; "
        "END IF; END $$;"
    )


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "status",
            enum_type(ConversationStatus, "conversation_status"),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "agent_context",
            enum_type(AgentContext, "agent_context"),
            server_default=sa.text("'general'"),
            nullable=False,
        ),
        sa.Column(
            "pinned",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "message_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_conversations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"status IN ({_STATUS_VALUES})",
            name="status_valid",
        ),
        sa.CheckConstraint(
            f"agent_context IN ({_AGENT_CONTEXT_VALUES})",
            name="agent_context_valid",
        ),
        sa.CheckConstraint(
            "message_count >= 0",
            name="message_count_non_negative",
        ),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_index(
        "ix_conversations_user_id_status",
        "conversations",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_conversations_user_id_last_message_at",
        "conversations",
        ["user_id", "last_message_at"],
    )
    op.create_index(
        "ix_conversations_user_id_deleted_at",
        "conversations",
        ["user_id", "deleted_at"],
    )

    # RLS: tenant isolation keyed on the per-transaction GUC (fail-closed).
    op.execute("ALTER TABLE conversations ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY conversations_tenant_isolation ON conversations "
        f"FOR ALL USING (user_id = {_GUC}) "
        f"WITH CHECK (user_id = {_GUC})"
    )

    # Grant the non-bypass app role on this table. ALTER DEFAULT PRIVILEGES does
    # not reliably cover owner-created migration tables (role-context mismatch),
    # so the grant travels with the table. Conditional: a no-op on environments
    # where the role does not exist yet (the role is provisioned out-of-band).
    _grant_app_role("conversations")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS conversations_tenant_isolation ON conversations")
    op.execute("ALTER TABLE conversations DISABLE ROW LEVEL SECURITY")
    op.drop_table("conversations")
