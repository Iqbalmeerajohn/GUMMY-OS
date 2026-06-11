"""add tool_invocations audit table (Phase 3, M6)

Revision ID: 0015_add_tool_invocations
Revises: 0014_add_agent_messages
Create Date: 2026-06-11

The append-only audit of every tool call through the Tool Execution
Interface: args, tier, the policy gate's decision (allowed|blocked|pending),
execution status, and cost. Standard fail-closed direct-column RLS +
conditional ``gummy_app`` grant — the Phase 2 pattern.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.enums import PermissionTier, ToolDecision, ToolRunStatus

# revision identifiers, used by Alembic.
revision: str = "0015_add_tool_invocations"
down_revision: str | None = "0014_add_agent_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

_TIER_VALUES = ", ".join(f"'{t.value}'" for t in PermissionTier)
_DECISION_VALUES = ", ".join(f"'{d.value}'" for d in ToolDecision)
_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in ToolRunStatus)


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
        "tool_invocations",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("agent_key", sa.String(length=64), nullable=False),
        sa.Column("tool_key", sa.String(length=64), nullable=False),
        sa.Column("args", postgresql.JSONB(), nullable=True),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("output_ref", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "cost_tokens",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(precision=12, scale=6),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tool_invocations"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tool_invocations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_tool_invocations_run_id_agent_runs",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"tier IN ({_TIER_VALUES})",
            name="tier_valid",
        ),
        sa.CheckConstraint(
            f"decision IN ({_DECISION_VALUES})",
            name="decision_valid",
        ),
        sa.CheckConstraint(
            f"status IN ({_STATUS_VALUES})",
            name="status_valid",
        ),
        sa.CheckConstraint(
            "cost_tokens >= 0",
            name="cost_tokens_non_negative",
        ),
    )
    op.create_index(
        "ix_tool_invocations_user_id", "tool_invocations", ["user_id"]
    )
    op.create_index(
        "ix_tool_invocations_run_id", "tool_invocations", ["run_id"]
    )

    op.execute("ALTER TABLE tool_invocations ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tool_invocations_tenant_isolation ON tool_invocations "
        f"FOR ALL USING (user_id = {_GUC}) "
        f"WITH CHECK (user_id = {_GUC})"
    )
    _grant_app_role("tool_invocations")


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS tool_invocations_tenant_isolation "
        "ON tool_invocations"
    )
    op.execute("ALTER TABLE tool_invocations DISABLE ROW LEVEL SECURITY")
    op.drop_table("tool_invocations")
