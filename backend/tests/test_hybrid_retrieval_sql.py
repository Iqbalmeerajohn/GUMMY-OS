"""The SQL hybrid retrieval actually emits, checked against Postgres' dialect.

The unit suite runs on SQLite, which silently accepts things Postgres rejects.
That gap shipped a real defect: the full-text half bound its text-search config
as a parameter, rendering ``to_tsvector($1::VARCHAR, content)``. Postgres has no
such overload — only ``to_tsvector(regconfig, text)`` — so every full-text query
raised, and because document search degrades to keyword matching rather than
failing loudly, nothing visibly broke. Hybrid retrieval was quietly running on
one leg.

Compiling against the PostgreSQL dialect catches that class of bug without a
live database: no connection is made, only SQL text is produced.
"""

from __future__ import annotations

import uuid

from sqlalchemy.dialects import postgresql

from app.services.files import hybrid_retrieval

# The exact expression indexed by ix_file_chunks_content_fts (migration 0026).
# Postgres only uses an expression index when the query expression is identical,
# so this string is a contract between the migration and the query.
INDEXED_EXPRESSION = "to_tsvector('english', file_chunks.content)"


def _compiled_text_query() -> str:
    """Render the lexical half as Postgres would receive it."""
    stmt = hybrid_retrieval._text_candidates_stmt(
        user_id=uuid.uuid4(), terms="salary or employee", limit=30, file_id=None
    )
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_text_search_config_is_not_a_bound_parameter() -> None:
    """The regression: a bound config has no matching Postgres overload."""
    sql = _compiled_text_query()
    assert "::VARCHAR, file_chunks.content" not in sql
    assert "to_tsvector('english'" in sql


def test_query_expression_matches_the_indexed_expression() -> None:
    """Spelled differently, the GIN index is skipped and this scans the table."""
    assert INDEXED_EXPRESSION in _compiled_text_query()


def test_websearch_to_tsquery_also_takes_a_literal_config() -> None:
    assert "websearch_to_tsquery('english'" in _compiled_text_query()


def test_tenant_filter_is_present_in_the_statement() -> None:
    """Ownership is enforced by the query, not only by RLS.

    Retrieval is the last place to depend on a single layer: a policy that is
    accidentally dropped should still not hand one user another's documents.
    """
    assert "file_chunks.user_id = " in _compiled_text_query()
