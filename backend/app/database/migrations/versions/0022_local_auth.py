"""local identity: password + Google OAuth columns, and refresh tokens

Revision ID: 0022_local_auth
Revises: 0021_add_files
Create Date: 2026-08-12

GUMMY becomes its own identity provider, replacing Supabase Auth. ``users``
gains the credential and profile columns that Supabase previously owned, and
``refresh_tokens`` makes sessions revocable.

Two deliberate choices:

* **Refresh tokens are stored hashed** (SHA-256), never in plaintext. A dump of
  this table therefore cannot be replayed as a session — the same reason
  passwords are hashed. The lookup is by hash, so it stays a single indexed read.
* **``password_hash`` is nullable.** A Google-only account has no password, and
  forcing a placeholder there would make "has no password" indistinguishable
  from "has an unusable one".

``users`` keeps its existing ``id = GUC`` RLS policy; the auth flow queries it
through the owner connection because a login must find the account *before* the
tenant is known.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0022_local_auth"
down_revision: str | None = "0021_add_files"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"


def upgrade() -> None:
    # ── users: credentials + profile previously held by Supabase ─────────────
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("display_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.String(1024), nullable=True))
    # Google's `sub` claim: stable per (account, OAuth client) and never reused,
    # unlike email which a user can change. This is the real join key.
    op.add_column("users", sa.Column("google_sub", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("uq_users_google_sub", "users", ["google_sub"], unique=True)

    # ── refresh_tokens: revocable, rotating sessions ─────────────────────────
    op.create_table(
        "refresh_tokens",
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
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "uq_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    # Standard fail-closed tenant isolation (matches every other tenant table).
    op.execute("ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY refresh_tokens_tenant_isolation ON refresh_tokens "
        f"FOR ALL USING (user_id = {_GUC}) "
        f"WITH CHECK (user_id = {_GUC})"
    )
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gummy_app') THEN "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON refresh_tokens TO gummy_app; "
        "END IF; END $$;"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS refresh_tokens_tenant_isolation ON refresh_tokens"
    )
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("uq_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("uq_users_google_sub", table_name="users")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "google_sub")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "display_name")
    op.drop_column("users", "password_hash")
