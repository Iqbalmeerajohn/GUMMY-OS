"""widen memory_sources.source_kind to agent/document/activity (Phase 3, M7)

Revision ID: 0016_widen_source_kind
Revises: 0015_add_tool_invocations
Create Date: 2026-06-11

The "shared provenance bus" seam Phase 2 named: agent-proposed memories carry
``source_kind='agent'``; ``document`` and ``activity`` are reserved for the
phases that introduce those sources. Constraint-only change — no data
migration, existing ``conversation`` rows untouched.

Downgrade restores the Phase 2 single-value CHECK; it is safe only while no
widened-kind rows exist (i.e. with agent memory writes flag-off), which is
the only state a rollback would run from.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.models.enums import SourceKind

# revision identifiers, used by Alembic.
revision: str = "0016_widen_source_kind"
down_revision: str | None = "0015_add_tool_invocations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Unprefixed: Alembic applies the metadata naming convention to BOTH
# create_check_constraint and drop_constraint, expanding this to
# ck_memory_sources_source_kind_valid (the live constraint's actual name).
_CONSTRAINT = "source_kind_valid"
_TABLE = "memory_sources"

_NEW_VALUES = ", ".join(f"'{k.value}'" for k in SourceKind)
_OLD_VALUES = "'conversation'"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        f"source_kind IN ({_NEW_VALUES})",
    )


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(
        _CONSTRAINT,
        _TABLE,
        f"source_kind IN ({_OLD_VALUES})",
    )
