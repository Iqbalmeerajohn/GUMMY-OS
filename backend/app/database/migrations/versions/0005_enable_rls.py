"""enable row-level security (tenant isolation)

Revision ID: 0005_enable_rls
Revises: 0004_add_memory_recall_tracking
Create Date: 2026-06-08

Phase 1.5 Increment B. Adds ``memory_embeddings.user_id`` (backfilled) and enables
Row-Level Security on every tenant table. Policies key off the per-transaction GUC
``app.current_user_id`` (set by the app's ``after_begin`` hook); when unset,
``current_setting(..., true)`` is NULL and rows are hidden — i.e. **fail closed**.

The dedicated non-bypass application role (``gummy_app``) is created out-of-band
as a one-time ops step (cluster privilege), not here — see
docs/PHASE1_5_RLS_OPS.md. Table owners / ``service_role`` bypass RLS, so the app
keeps working on its current connection until it is switched to ``gummy_app``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_enable_rls"
down_revision: str | None = "0004_add_memory_recall_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# NULLIF guards the empty-string case: a custom GUC reverts to '' (not NULL) once
# referenced in a session, and ''::uuid would raise. NULLIF -> NULL -> no rows
# (graceful fail-closed) when the tenant is unset.
_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"

# Tables with a direct tenant column (`users` is keyed by its own id).
_COLUMN_RLS: list[tuple[str, str]] = [
    ("users", "id"),
    ("memories", "user_id"),
    ("memory_embeddings", "user_id"),
]

# memory_versions has no user_id; it is scoped through its parent memory. The
# inner SELECT is itself subject to the memories policy, so it resolves to "the
# memories this tenant can see".
_VERSIONS_PREDICATE = f"memory_id IN (SELECT id FROM memories WHERE user_id = {_GUC})"

# All tenant tables (for enable/disable + policy drop).
_ALL_RLS_TABLES = [t for t, _ in _COLUMN_RLS] + ["memory_versions"]


def upgrade() -> None:
    # 1) Add memory_embeddings.user_id, backfill from the parent memory, lock down.
    op.add_column(
        "memory_embeddings",
        sa.Column("user_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        "UPDATE memory_embeddings me SET user_id = m.user_id "
        "FROM memories m WHERE me.memory_id = m.id"
    )
    op.alter_column("memory_embeddings", "user_id", nullable=False)
    op.create_foreign_key(
        "fk_memory_embeddings_user_id_users",
        "memory_embeddings",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_memory_embeddings_user_id", "memory_embeddings", ["user_id"])

    # 2) Enable RLS + a tenant-isolation policy (USING + WITH CHECK) per table.
    for table, column in _COLUMN_RLS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"FOR ALL USING ({column} = {_GUC}) "
            f"WITH CHECK ({column} = {_GUC})"
        )

    # memory_versions: scoped via parent memory (no own user_id column).
    op.execute("ALTER TABLE memory_versions ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY memory_versions_tenant_isolation ON memory_versions "
        f"FOR ALL USING ({_VERSIONS_PREDICATE}) "
        f"WITH CHECK ({_VERSIONS_PREDICATE})"
    )


def downgrade() -> None:
    for table in _ALL_RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_memory_embeddings_user_id", table_name="memory_embeddings")
    op.drop_constraint(
        "fk_memory_embeddings_user_id_users",
        "memory_embeddings",
        type_="foreignkey",
    )
    op.drop_column("memory_embeddings", "user_id")
