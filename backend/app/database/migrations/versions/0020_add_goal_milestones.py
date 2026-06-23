"""add goal_milestones table (M5 Goals System)

Revision ID: 0020_add_goal_milestones
Revises: 0019_goals_m5_fields
Create Date: 2026-06-23

Milestones decompose a goal into ordered, user-managed checklist steps; the
ratio of completed to total milestones drives a goal's derived progress.
``goal_id`` is ``ON DELETE CASCADE`` (milestones have no life without their
goal). Denormalized ``user_id`` carries the standard fail-closed,
direct-column RLS policy and the conditional ``gummy_app`` grant.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020_add_goal_milestones"
down_revision: str | None = "0019_goals_m5_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"


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
        "goal_milestones",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "completed",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "order_index",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_goal_milestones"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_goal_milestones_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["goal_id"],
            ["goals.id"],
            name="fk_goal_milestones_goal_id_goals",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_goal_milestones_user_id", "goal_milestones", ["user_id"]
    )
    op.create_index(
        "ix_goal_milestones_goal_id", "goal_milestones", ["goal_id"]
    )

    op.execute("ALTER TABLE goal_milestones ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY goal_milestones_tenant_isolation ON goal_milestones "
        f"FOR ALL USING (user_id = {_GUC}) "
        f"WITH CHECK (user_id = {_GUC})"
    )
    _grant_app_role("goal_milestones")


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS goal_milestones_tenant_isolation "
        "ON goal_milestones"
    )
    op.execute("ALTER TABLE goal_milestones DISABLE ROW LEVEL SECURITY")
    op.drop_table("goal_milestones")
