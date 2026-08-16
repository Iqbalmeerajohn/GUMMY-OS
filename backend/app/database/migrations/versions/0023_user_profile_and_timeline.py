"""learned user profile + episodic time anchor on memories

Revision ID: 0023_user_profile_timeline
Revises: 0022_local_auth
Create Date: 2026-08-12

Two additions that make memory feel like it knows the person, not just facts:

* **``user_profiles``** — one row per user holding the portrait GUMMY maintains
  by itself: the traits it has settled on (name, location, work, focus), how the
  person tends to write, and their emotional baseline. It exists as a table
  rather than being recomputed per turn because it must be readable in a single
  indexed row-fetch: it is injected into *every* prompt, including the first
  message of a brand-new conversation, and a multi-query rebuild there would
  cost more than the answer.

* **``memories.occurred_at``** — when the remembered thing *happened*, as
  opposed to when it was stored (``created_at``). Without it "what did I do last
  week?" is unanswerable: a fact learned today about last Tuesday sorts as
  today. Nullable, because most facts ("Lives in Vizag") are not events.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0023_user_profile_timeline"
down_revision: str | None = "0022_local_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GUC = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"


def upgrade() -> None:
    # ── memories: when it happened ───────────────────────────────────────────
    op.add_column(
        "memories",
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial index: only event memories carry the column, and the timeline only
    # ever reads those — so the index stays small no matter how many facts exist.
    op.execute(
        "CREATE INDEX ix_memories_user_id_occurred_at "
        "ON memories (user_id, occurred_at DESC) "
        "WHERE occurred_at IS NOT NULL"
    )

    # ── user_profiles: the portrait GUMMY maintains ──────────────────────────
    op.create_table(
        "user_profiles",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        # Settled facts, keyed by trait ("name", "location", "work", "focus").
        # JSONB rather than columns because the trait set is expected to grow and
        # each addition would otherwise be a migration.
        sa.Column(
            "traits",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        # Running tally of detected moods, e.g. {"stressed": 3, "positive": 11}.
        sa.Column(
            "mood_counts",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "message_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        # Mean characters per user message — a cheap, honest proxy for whether
        # this person writes in fragments or paragraphs, which is what the reply
        # length should mirror.
        sa.Column(
            "avg_message_chars",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Standard fail-closed tenant isolation (matches every other tenant table).
    op.execute("ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY user_profiles_tenant_isolation ON user_profiles "
        f"FOR ALL USING (user_id = {_GUC}) "
        f"WITH CHECK (user_id = {_GUC})"
    )
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gummy_app') THEN "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON user_profiles TO gummy_app; "
        "END IF; END $$;"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS user_profiles_tenant_isolation ON user_profiles")
    op.drop_table("user_profiles")
    op.execute("DROP INDEX IF EXISTS ix_memories_user_id_occurred_at")
    op.drop_column("memories", "occurred_at")
