"""add agents registry catalog table (Phase 3, M1)

Revision ID: 0012_add_agents
Revises: 0011_extraction_watermark
Create Date: 2026-06-11

The Agent Registry catalog. Built-in (global) agents have ``user_id IS NULL``
and must be readable by every tenant but writable only outside a tenant
transaction (the startup seed path runs with no GUC set); user-defined rows
(future) follow the standard fail-closed tenant policy. Hence three policies
instead of the usual one — see docs/PHASE3_PLAN.md §5.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.enums import PermissionTier

# revision identifiers, used by Alembic.
revision: str = "0012_add_agents"
down_revision: str | None = "0011_extraction_watermark"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

_CEILING_VALUES = ", ".join(f"'{t.value}'" for t in PermissionTier)


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
        "agents",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("mission", sa.Text(), nullable=False),
        sa.Column(
            "ceiling",
            sa.String(length=32),
            server_default=sa.text("'green'"),
            nullable=False,
        ),
        sa.Column(
            "tool_manifest",
            postgresql.JSONB(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("model_tier", sa.String(length=32), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
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
        sa.PrimaryKeyConstraint("id", name="pk_agents"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_agents_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("key", name="uq_agents_key"),
        sa.CheckConstraint(
            f"ceiling IN ({_CEILING_VALUES})",
            name="ceiling_valid",
        ),
    )
    op.create_index("ix_agents_user_id", "agents", ["user_id"])

    # RLS. Global catalog rows (user_id IS NULL) are readable by every tenant
    # but writable only when NO tenant GUC is set (the startup seed path);
    # user-defined rows follow the standard fail-closed tenant policy.
    op.execute("ALTER TABLE agents ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY agents_global_read ON agents "
        "FOR SELECT USING (user_id IS NULL)"
    )
    op.execute(
        "CREATE POLICY agents_tenant_isolation ON agents "
        f"FOR ALL USING (user_id = {_GUC}) "
        f"WITH CHECK (user_id = {_GUC})"
    )
    op.execute(
        "CREATE POLICY agents_global_seed ON agents "
        f"FOR ALL USING (user_id IS NULL AND {_GUC} IS NULL) "
        f"WITH CHECK (user_id IS NULL AND {_GUC} IS NULL)"
    )
    _grant_app_role("agents")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS agents_global_seed ON agents")
    op.execute("DROP POLICY IF EXISTS agents_tenant_isolation ON agents")
    op.execute("DROP POLICY IF EXISTS agents_global_read ON agents")
    op.execute("ALTER TABLE agents DISABLE ROW LEVEL SECURITY")
    op.drop_table("agents")
