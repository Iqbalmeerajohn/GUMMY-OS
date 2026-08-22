"""file chunk embeddings, full-text index, checksum and indexed_at

Revision ID: 0026_file_chunk_embeddings
Revises: 0025_password_reset_tokens
Create Date: 2026-08-22

The RAG half of the files system. Chunks have existed since M6 — deterministic,
tenant-scoped, ready to embed — but nothing ever embedded them, so document
search was ``ILIKE '%query%'`` with the ranking done in Python.

Three decisions worth stating.

**The vector lives on ``file_chunks``, not in a side table.** ``memory_embeddings``
is a separate table because a memory may carry one embedding per model, and the
uniqueness constraint on ``(memory_id, embedding_model)`` is what makes that
safe. A chunk has no such requirement: it is embedded once, by whichever model
the instance is configured with, and re-embedded wholesale on re-index. A side
table would add a join to the hottest read path for flexibility nothing uses.
The cost is that changing embedding model means re-indexing every document,
which the re-index path already does.

**Both indexes, not one.** HNSW answers "what is semantically near this?" and
GIN/tsvector answers "which chunks literally contain this word?". Vector search
alone misses exact identifiers — a surname, ``BiLSTM``, a column header — that
embeddings smear into their neighbourhood. The retrieval layer merges them.

**``checksum`` is unique per user, not globally.** Two people uploading the same
public PDF each keep their own copy; the same person uploading it twice does
not. Scoping it globally would leak the existence of another tenant's file
through a duplicate-detection response.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from app.core.constants import EMBEDDING_DIMENSION

# revision identifiers, used by Alembic.
revision: str = "0026_file_chunk_embeddings"
down_revision: str | None = "0025_password_reset_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── files: provenance + indexing lifecycle ───────────────────────────────
    op.add_column("files", sa.Column("checksum", sa.String(64), nullable=True))
    op.add_column(
        "files",
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Per-tenant uniqueness. Partial, so the many rows predating this migration
    # (checksum NULL) do not collide with each other.
    op.execute(
        "CREATE UNIQUE INDEX uq_files_user_id_checksum "
        "ON files (user_id, checksum) WHERE checksum IS NOT NULL"
    )

    # ── file_chunks: the vector, and the two indexes over it ─────────────────
    op.add_column(
        "file_chunks",
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION), nullable=True),
    )
    op.add_column(
        "file_chunks", sa.Column("embedding_model", sa.String(128), nullable=True)
    )
    op.execute(
        "CREATE INDEX ix_file_chunks_embedding "
        "ON file_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    # Postgres English full-text over chunk content. Mirrors the messages index
    # added in 0007 — the same shape, for the same reason.
    op.execute(
        "CREATE INDEX ix_file_chunks_content_fts "
        "ON file_chunks USING gin (to_tsvector('english', content))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_file_chunks_content_fts")
    op.execute("DROP INDEX IF EXISTS ix_file_chunks_embedding")
    op.drop_column("file_chunks", "embedding_model")
    op.drop_column("file_chunks", "embedding")
    op.execute("DROP INDEX IF EXISTS uq_files_user_id_checksum")
    op.drop_column("files", "indexed_at")
    op.drop_column("files", "checksum")
