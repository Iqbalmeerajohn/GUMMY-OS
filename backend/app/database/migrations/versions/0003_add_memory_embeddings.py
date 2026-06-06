"""add pgvector + memory_embeddings

Revision ID: 0003_add_memory_embeddings
Revises: 0002_add_memory_soft_delete
Create Date: 2026-06-07

Day 4 of Phase 1 — enables the pgvector extension and adds the ``memory_embeddings``
table that backs semantic search. An HNSW index with cosine ops powers fast ANN
retrieval. No embeddings/retrieval business logic lives here.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from app.core.constants import EMBEDDING_DIMENSION

# revision identifiers, used by Alembic.
revision: str = "0003_add_memory_embeddings"
down_revision: str | None = "0002_add_memory_soft_delete"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "memory_embeddings",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("memory_id", sa.Uuid(), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_vector", Vector(EMBEDDING_DIMENSION), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_embeddings"),
        sa.ForeignKeyConstraint(
            ["memory_id"],
            ["memories.id"],
            name="fk_memory_embeddings_memory_id_memories",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "memory_id",
            "embedding_model",
            name="uq_memory_embeddings_memory_id_embedding_model",
        ),
    )
    op.create_index(
        "ix_memory_embeddings_memory_id", "memory_embeddings", ["memory_id"]
    )
    # Approximate-nearest-neighbour index for cosine similarity search.
    op.execute(
        "CREATE INDEX ix_memory_embeddings_vector "
        "ON memory_embeddings USING hnsw (embedding_vector vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_memory_embeddings_vector", table_name="memory_embeddings")
    op.drop_table("memory_embeddings")
    # The `vector` extension is left installed; it may be used elsewhere.
