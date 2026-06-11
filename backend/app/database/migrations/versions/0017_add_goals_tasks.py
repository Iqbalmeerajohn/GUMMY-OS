"""add goals + tasks foundation tables (Phase 3, M8)

Revision ID: 0017_add_goals_tasks
Revises: 0016_widen_source_kind
Create Date: 2026-06-11

The durable work backbone: goals (what the user wants) decomposed into tasks
(units of agent work with status). ``tasks.goal_id`` and
``tasks.agent_run_id`` are ``ON DELETE SET NULL`` so work records survive
goal/run cleanup. Both tables: denormalized ``user_id``, fail-closed
direct-column RLS in this migration, conditional ``gummy_app`` grant.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.enums import AgentContext, GoalStatus, TaskStatus

# revision identifiers, used by Alembic.
revision: str = "0017_add_goals_tasks"
down_revision: str | None = "0016_widen_source_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

_GOAL_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in GoalStatus)
_TASK_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in TaskStatus)
_AGENT_CONTEXT_VALUES = ", ".join(f"'{a.value}'" for a in AgentContext)


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
        "goals",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "agent_context",
            sa.String(length=32),
            server_default=sa.text("'general'"),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_goals"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_goals_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"status IN ({_GOAL_STATUS_VALUES})",
            name="status_valid",
        ),
        sa.CheckConstraint(
            f"agent_context IN ({_AGENT_CONTEXT_VALUES})",
            name="agent_context_valid",
        ),
    )
    op.create_index("ix_goals_user_id", "goals", ["user_id"])
    op.create_index("ix_goals_user_id_status", "goals", ["user_id", "status"])
    _enable_rls("goals")
    _grant_app_role("goals")

    op.create_table(
        "tasks",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=True),
        sa.Column("agent_key", sa.String(length=64), nullable=True),
        sa.Column("agent_run_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "seq",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("result_ref", postgresql.JSONB(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_tasks_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["goals.id"],
            name="fk_tasks_goal_id_goals",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name="fk_tasks_agent_run_id_agent_runs",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            f"status IN ({_TASK_STATUS_VALUES})",
            name="status_valid",
        ),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])
    op.create_index("ix_tasks_user_id_status", "tasks", ["user_id", "status"])
    op.create_index("ix_tasks_goal_id", "tasks", ["goal_id"])
    _enable_rls("tasks")
    _grant_app_role("tasks")


def downgrade() -> None:
    for table in ("tasks", "goals"):
        op.execute(
            f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"
        )
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("tasks")
    op.drop_table("goals")
