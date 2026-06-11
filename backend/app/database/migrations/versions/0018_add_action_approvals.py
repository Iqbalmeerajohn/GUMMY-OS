"""add action_approvals human-in-the-loop table (Phase 3, M10)

Revision ID: 0018_add_action_approvals
Revises: 0017_add_goals_tasks
Create Date: 2026-06-11

The approval seam: the Policy gate's "prompt" path creates a previewed
pending row; approve/reject records the decision (no executor exists in
Phase 3, so approving never fires a side effect). ``run_id`` is
``ON DELETE SET NULL`` so the decision trail survives run cleanup. Standard
fail-closed direct-column RLS + conditional ``gummy_app`` grant.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.enums import ApprovalStatus, PermissionTier

# revision identifiers, used by Alembic.
revision: str = "0018_add_action_approvals"
down_revision: str | None = "0017_add_goals_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in ApprovalStatus)
_TIER_VALUES = ", ".join(f"'{t.value}'" for t in PermissionTier)


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
        "action_approvals",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("agent_key", sa.String(length=64), nullable=False),
        sa.Column("action_kind", sa.String(length=64), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("preview", postgresql.JSONB(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name="pk_action_approvals"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_action_approvals_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name="fk_action_approvals_run_id_agent_runs",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            f"status IN ({_STATUS_VALUES})",
            name="status_valid",
        ),
        sa.CheckConstraint(
            f"tier IN ({_TIER_VALUES})",
            name="tier_valid",
        ),
    )
    op.create_index(
        "ix_action_approvals_user_id", "action_approvals", ["user_id"]
    )
    op.create_index(
        "ix_action_approvals_user_id_status",
        "action_approvals",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_action_approvals_run_id", "action_approvals", ["run_id"]
    )

    op.execute("ALTER TABLE action_approvals ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY action_approvals_tenant_isolation ON action_approvals "
        f"FOR ALL USING (user_id = {_GUC}) "
        f"WITH CHECK (user_id = {_GUC})"
    )
    _grant_app_role("action_approvals")


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS action_approvals_tenant_isolation "
        "ON action_approvals"
    )
    op.execute("ALTER TABLE action_approvals DISABLE ROW LEVEL SECURITY")
    op.drop_table("action_approvals")
