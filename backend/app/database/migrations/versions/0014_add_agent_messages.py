"""add agent_messages inter-agent audit table (Phase 3, M1)

Revision ID: 0014_add_agent_messages
Revises: 0013_add_agent_runs
Create Date: 2026-06-11

The append-only inter-agent audit trail: every orchestrator-mediated hop
(task hand-off, result, error) is one row, ordered by ``UNIQUE(run_id, seq)``.
Standard fail-closed direct-column RLS + conditional ``gummy_app`` grant.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.enums import AgentMessageRole

# revision identifiers, used by Alembic.
revision: str = "0014_add_agent_messages"
down_revision: str | None = "0013_add_agent_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

_ROLE_VALUES = ", ".join(f"'{r.value}'" for r in AgentMessageRole)


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
        "agent_messages",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("from_agent", sa.String(length=64), nullable=False),
        sa.Column("to_agent", sa.String(length=64), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_messages"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_agent_messages_run_id_agent_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_agent_messages_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("run_id", "seq", name="uq_agent_messages_run_id_seq"),
        sa.CheckConstraint(
            f"role IN ({_ROLE_VALUES})",
            name="role_valid",
        ),
    )
    op.create_index("ix_agent_messages_run_id", "agent_messages", ["run_id"])
    op.create_index("ix_agent_messages_user_id", "agent_messages", ["user_id"])

    op.execute("ALTER TABLE agent_messages ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY agent_messages_tenant_isolation ON agent_messages "
        f"FOR ALL USING (user_id = {_GUC}) "
        f"WITH CHECK (user_id = {_GUC})"
    )
    _grant_app_role("agent_messages")


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS agent_messages_tenant_isolation " "ON agent_messages"
    )
    op.execute("ALTER TABLE agent_messages DISABLE ROW LEVEL SECURITY")
    op.drop_table("agent_messages")
