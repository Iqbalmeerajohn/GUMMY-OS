"""evolve goals into the M5 user-facing model (status/priority/progress)

Revision ID: 0019_goals_m5_fields
Revises: 0018_add_action_approvals
Create Date: 2026-06-23

M5 elevates goals from the M8 agent scaffold to a first-class, user-facing
feature. This migration, in place on the existing ``goals`` table:

* Re-scopes ``status`` to ``active | completed | archived`` (mapping the old
  ``done`` → ``completed``, ``paused`` → ``active``, ``abandoned`` →
  ``archived``) and swaps the CHECK constraint.
* Converts ``priority`` from an integer (0–100) to the enum
  ``low | medium | high`` (bucketing existing values) with a CHECK.
* Adds ``category``, ``progress_percentage`` (0–100, CHECK), and
  ``completed_at``.

RLS, indexes, and the ``gummy_app`` grant from 0017 are unaffected.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.models.enums import GoalPriority, GoalStatus

# revision identifiers, used by Alembic.
revision: str = "0019_goals_m5_fields"
down_revision: str | None = "0018_add_action_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in GoalStatus)
_PRIORITY_VALUES = ", ".join(f"'{p.value}'" for p in GoalPriority)


def upgrade() -> None:
    # ── New columns ───────────────────────────────────────────────────────────
    op.add_column("goals", sa.Column("category", sa.Text(), nullable=True))
    op.add_column(
        "goals",
        sa.Column(
            "progress_percentage",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "goals",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "progress_percentage_range",
        "goals",
        "progress_percentage >= 0 AND progress_percentage <= 100",
    )

    # ── status: re-map legacy values, then swap the CHECK ─────────────────────
    op.execute("UPDATE goals SET status = 'completed' WHERE status = 'done'")
    op.execute("UPDATE goals SET status = 'active' WHERE status = 'paused'")
    op.execute(
        "UPDATE goals SET status = 'archived' WHERE status = 'abandoned'"
    )
    op.drop_constraint("status_valid", "goals", type_="check")
    op.create_check_constraint(
        "status_valid", "goals", f"status IN ({_STATUS_VALUES})"
    )

    # ── priority: int (0–100) → enum (low/medium/high) ────────────────────────
    op.execute("ALTER TABLE goals ALTER COLUMN priority DROP DEFAULT")
    op.execute(
        "ALTER TABLE goals ALTER COLUMN priority TYPE VARCHAR(16) USING ("
        "CASE WHEN priority >= 67 THEN 'high' "
        "WHEN priority >= 34 THEN 'medium' ELSE 'low' END)"
    )
    op.execute("ALTER TABLE goals ALTER COLUMN priority SET DEFAULT 'medium'")
    op.create_check_constraint(
        "priority_valid", "goals", f"priority IN ({_PRIORITY_VALUES})"
    )


def downgrade() -> None:
    # priority enum → int
    op.drop_constraint("priority_valid", "goals", type_="check")
    op.execute("ALTER TABLE goals ALTER COLUMN priority DROP DEFAULT")
    op.execute(
        "ALTER TABLE goals ALTER COLUMN priority TYPE INTEGER USING ("
        "CASE WHEN priority = 'high' THEN 100 "
        "WHEN priority = 'medium' THEN 50 ELSE 0 END)"
    )
    op.execute("ALTER TABLE goals ALTER COLUMN priority SET DEFAULT 0")

    # status back to the legacy four-value domain
    op.drop_constraint("status_valid", "goals", type_="check")
    op.execute("UPDATE goals SET status = 'done' WHERE status = 'completed'")
    op.create_check_constraint(
        "status_valid",
        "goals",
        "status IN ('active', 'paused', 'done', 'abandoned')",
    )

    op.drop_constraint("progress_percentage_range", "goals", type_="check")
    op.drop_column("goals", "completed_at")
    op.drop_column("goals", "progress_percentage")
    op.drop_column("goals", "category")
