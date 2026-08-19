"""password reset tokens

Revision ID: 0025_password_reset_tokens
Revises: 0024_add_automations
Create Date: 2026-08-19

Password recovery for GUMMY's own identity provider. The login screen has
linked to a reset flow since the local-auth migration, but nothing served it —
this table is the durable half of closing that.

Modelled directly on ``refresh_tokens``, for the same reason: only the SHA-256
**hash** of the token is stored, so this table cannot be replayed as a set of
live reset links if it is ever dumped. The raw token exists only in the
delivered link and in the request that redeems it.

``used_at`` marks a token spent instead of deleting the row, which lets
redemption tell "never issued" apart from "already used", and leaves evidence
that the reset happened.

RLS matches every other tenant table (fail-closed on ``app.current_user_id``),
though in practice the reset flow runs on the owner connection: a user who has
forgotten their password cannot have established a tenant context.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0025_password_reset_tokens"
down_revision: str | None = "0024_add_automations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "uq_password_reset_tokens_token_hash",
        "password_reset_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"]
    )

    # Standard fail-closed tenant isolation (matches every other tenant table).
    op.execute("ALTER TABLE password_reset_tokens ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY password_reset_tokens_tenant_isolation ON password_reset_tokens "
        f"FOR ALL USING (user_id = {_GUC}) "
        f"WITH CHECK (user_id = {_GUC})"
    )
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gummy_app') THEN "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset_tokens TO gummy_app; "
        "END IF; END $$;"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS password_reset_tokens_tenant_isolation "
        "ON password_reset_tokens"
    )
    op.drop_index(
        "ix_password_reset_tokens_user_id", table_name="password_reset_tokens"
    )
    op.drop_index(
        "uq_password_reset_tokens_token_hash", table_name="password_reset_tokens"
    )
    op.drop_table("password_reset_tokens")
