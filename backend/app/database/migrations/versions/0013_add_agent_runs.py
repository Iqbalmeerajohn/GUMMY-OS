"""add agent_runs + agent_steps trace tables (Phase 3, M1)

Revision ID: 0013_add_agent_runs
Revises: 0012_add_agents
Create Date: 2026-06-11

The orchestration observability trace: one ``agent_runs`` row per
orchestration, child ``agent_steps`` per agent invocation.
``conversation_id`` is ``ON DELETE SET NULL`` so the audit/cost trail survives
thread deletion. Both tables: denormalized ``user_id``, fail-closed
direct-column RLS, conditional ``gummy_app`` grant — the Phase 2 pattern.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.enums import RunStatus, RunTrigger, StepStatus

# revision identifiers, used by Alembic.
revision: str = "0013_add_agent_runs"
down_revision: str | None = "0012_add_agents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

_RUN_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in RunStatus)
_TRIGGER_VALUES = ", ".join(f"'{t.value}'" for t in RunTrigger)
_STEP_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in StepStatus)


def _grant_app_role(table: str) -> None:
    """Grant CRUD on ``table`` to the non-bypass ``gummy_app`` role if it exists."""
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gummy_app') THEN "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gummy_app; "
        "END IF; END $$;"
    )


def _enable_rls(table: str) -> None:
    """Enable RLS with the standard fail-closed tenant policy."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON {table} "
        f"FOR ALL USING (user_id = {_GUC}) "
        f"WITH CHECK (user_id = {_GUC})"
    )


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column(
            "trigger",
            sa.String(length=32),
            server_default=sa.text("'chat'"),
            nullable=False,
        ),
        sa.Column("route_plan", postgresql.JSONB(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_agent_runs_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_agent_runs_conversation_id_conversations",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            f"status IN ({_RUN_STATUS_VALUES})",
            name="status_valid",
        ),
        sa.CheckConstraint(
            f"trigger IN ({_TRIGGER_VALUES})",
            name="trigger_valid",
        ),
        sa.CheckConstraint(
            "cost_tokens >= 0",
            name="cost_tokens_non_negative",
        ),
    )
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])
    op.create_index(
        "ix_agent_runs_conversation_id", "agent_runs", ["conversation_id"]
    )
    op.create_index(
        "ix_agent_runs_user_id_created_at",
        "agent_runs",
        ["user_id", "created_at"],
    )
    _enable_rls("agent_runs")
    _grant_app_role("agent_runs")

    op.create_table(
        "agent_steps",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("agent_key", sa.String(length=64), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column("input", postgresql.JSONB(), nullable=True),
        sa.Column("output", postgresql.JSONB(), nullable=True),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_steps"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_agent_steps_run_id_agent_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_agent_steps_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("run_id", "seq", name="uq_agent_steps_run_id_seq"),
        sa.CheckConstraint(
            f"status IN ({_STEP_STATUS_VALUES})",
            name="status_valid",
        ),
        sa.CheckConstraint(
            "cost_tokens >= 0",
            name="cost_tokens_non_negative",
        ),
    )
    op.create_index("ix_agent_steps_run_id", "agent_steps", ["run_id"])
    op.create_index("ix_agent_steps_user_id", "agent_steps", ["user_id"])
    _enable_rls("agent_steps")
    _grant_app_role("agent_steps")


def downgrade() -> None:
    for table in ("agent_steps", "agent_runs"):
        op.execute(
            f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"
        )
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("agent_steps")
    op.drop_table("agent_runs")
