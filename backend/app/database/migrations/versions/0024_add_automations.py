"""automations + automation_runs (local durable scheduling)

Revision ID: 0024_add_automations
Revises: 0023_user_profile_timeline
Create Date: 2026-08-18

Scheduled work that survives a restart.

The existing background workers are in-memory ``asyncio.Queue``s: everything
queued is lost when the process stops. That is acceptable for embedding and
enrichment, which are re-derivable from data already committed — it is not
acceptable for "remind me tomorrow at 9", where losing the job silently means
the reminder never arrives and nothing anywhere records that it should have.

So the schedule lives in Postgres, and the scheduler is a poller over it. No new
infrastructure: the database already running is the durable store.

``automation_runs`` carries a unique constraint on
``(automation_id, scheduled_for)``. Claiming a run means inserting that row, so
two workers racing, a restart replaying a window, or a clock moving backwards
all produce a constraint violation rather than a duplicate reminder. Idempotency
is a database guarantee here, not a convention the code has to remember.

Both tables are RLS-scoped, fail-closed, exactly like every other tenant table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0024_add_automations"
down_revision: str | None = "0023_user_profile_timeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "automations",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("schedule", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default=sa.text("'UTC'"),
            nullable=False,
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "failure_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("payload", sa.JSON(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_automations"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_automations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind IN ('reminder', 'goal_check_in', 'digest')",
            name="automation_kind_valid",
        ),
        sa.CheckConstraint(
            "schedule IN ('once', 'daily', 'weekly')", name="automation_schedule_valid"
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'failed')",
            name="automation_status_valid",
        ),
    )
    op.create_index("ix_automations_user_id", "automations", ["user_id"])
    # The scheduler's only query. Partial, so it stays small however many
    # completed automations accumulate over time.
    op.execute(
        "CREATE INDEX ix_automations_due ON automations (next_run_at) "
        "WHERE enabled AND status = 'active'"
    )

    op.create_table(
        "automation_runs",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("automation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'running'"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_automation_runs"),
        sa.ForeignKeyConstraint(
            ["automation_id"],
            ["automations.id"],
            name="fk_automation_runs_automation_id_automations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_automation_runs_user_id_users",
            ondelete="CASCADE",
        ),
        # The idempotency guarantee: one run per automation per slot.
        sa.UniqueConstraint(
            "automation_id",
            "scheduled_for",
            name="uq_automation_runs_automation_id_scheduled_for",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed')",
            name="automation_run_status_valid",
        ),
    )
    op.create_index("ix_automation_runs_user_id", "automation_runs", ["user_id"])
    op.create_index(
        "ix_automation_runs_automation_id", "automation_runs", ["automation_id"]
    )

    # ── RLS: fail-closed tenant isolation, as on every other tenant table ────
    for table in ("automations", "automation_runs"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"FOR ALL USING (user_id = {_GUC}) "
            f"WITH CHECK (user_id = {_GUC})"
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO gummy_app")


def downgrade() -> None:
    for table in ("automation_runs", "automations"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
    op.drop_table("automation_runs")
    op.execute("DROP INDEX IF EXISTS ix_automations_due")
    op.drop_table("automations")
