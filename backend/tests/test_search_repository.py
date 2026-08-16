"""Semantic search query-construction tests.

pgvector's ``<=>`` runs only on PostgreSQL, so these tests validate the *generated
SQL* by compiling against the PostgreSQL dialect (no database connection). Live
ranking is verified against Postgres (see the Day 4 verification steps).
"""

from __future__ import annotations

import uuid

from sqlalchemy.dialects import postgresql

from app.core.constants import EMBEDDING_DIMENSION
from app.models.enums import MemoryCategory
from app.repositories.search_repository import build_search_statement


def _compiled_sql(**kwargs: object) -> str:
    stmt = build_search_statement(
        user_id=uuid.uuid4(),
        query_vector=[0.0] * EMBEDDING_DIMENSION,
        embedding_model="fake-deterministic-v1",
        limit=5,
        **kwargs,  # type: ignore[arg-type]
    )
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_uses_cosine_distance_operator() -> None:
    sql = _compiled_sql().upper()
    assert "<=>" in sql
    assert "ORDER BY" in sql
    assert "LIMIT" in sql


def test_tenant_and_model_filters_present() -> None:
    sql = _compiled_sql().lower()
    assert "user_id" in sql
    assert "deleted_at" in sql
    assert "embedding_model" in sql


def test_active_only_by_default_archived_optional() -> None:
    default_sql = _compiled_sql().lower()
    archived_sql = _compiled_sql(include_archived=True).lower()
    # The default constrains status (active only); including archived drops it.
    assert default_sql.count("status") > archived_sql.count("status")


def test_category_filter_applied() -> None:
    sql = _compiled_sql(category=MemoryCategory.CAREER).lower()
    assert "category" in sql
    assert "join" in sql  # memories <-> memory_embeddings
