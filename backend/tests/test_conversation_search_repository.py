"""Conversation search query-construction tests (M7).

Full-text (``@@`` / ts_rank) and pgvector (``<=>``) run only on PostgreSQL, so
these validate the *generated SQL* by compiling against the PostgreSQL dialect (no
DB). Live ranking + tenant isolation are verified in test_rls_postgres.py.
"""

from __future__ import annotations

import uuid

from sqlalchemy.dialects import postgresql

from app.core.constants import EMBEDDING_DIMENSION
from app.repositories.conversation_search_repository import (
    build_keyword_statement,
    build_message_search_statement,
    build_summary_semantic_statement,
)


def _keyword_sql(**kwargs: object) -> str:
    stmt = build_keyword_statement(
        user_id=uuid.uuid4(), query="rtos scheduling", limit=10, **kwargs
    )  # type: ignore[arg-type]
    return str(stmt.compile(dialect=postgresql.dialect()))


def _semantic_sql(**kwargs: object) -> str:
    stmt = build_summary_semantic_statement(
        user_id=uuid.uuid4(),
        query_vector=[0.0] * EMBEDDING_DIMENSION,
        embedding_model="fake-deterministic-v1",
        limit=10,
        **kwargs,  # type: ignore[arg-type]
    )
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_keyword_uses_fulltext_match_and_rank() -> None:
    sql = _keyword_sql().lower()
    assert "to_tsvector" in sql
    assert "plainto_tsquery" in sql
    assert "ts_rank" in sql
    assert "@@" in sql
    assert "order by" in sql
    assert "limit" in sql


def test_keyword_is_tenant_scoped_and_excludes_deleted() -> None:
    sql = _keyword_sql().lower()
    assert "user_id" in sql
    assert "deleted_at" in sql
    # joins messages to conversations
    assert "join" in sql


def _message_sql(**kwargs: object) -> str:
    stmt = build_message_search_statement(
        user_id=uuid.uuid4(), query="rtos scheduling", limit=10, **kwargs
    )  # type: ignore[arg-type]
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_message_search_uses_fulltext_and_returns_content() -> None:
    sql = _message_sql().lower()
    assert "to_tsvector" in sql
    assert "plainto_tsquery" in sql
    assert "ts_rank" in sql
    assert "@@" in sql
    # keeps the message content + parent title for snippeting (not folded away)
    assert "messages.content" in sql
    assert "conversations.title" in sql
    assert "order by" in sql
    assert "limit" in sql


def test_message_search_is_tenant_scoped_and_excludes_deleted() -> None:
    sql = _message_sql().lower()
    assert "user_id" in sql
    assert "deleted_at" in sql
    assert "join" in sql


def test_semantic_uses_cosine_distance() -> None:
    sql = _semantic_sql().upper()
    assert "<=>" in sql
    assert "ORDER BY" in sql
    assert "LIMIT" in sql


def test_semantic_tenant_model_and_deleted_filters() -> None:
    sql = _semantic_sql().lower()
    assert "user_id" in sql
    assert "embedding_model" in sql
    assert "deleted_at" in sql
    assert "join" in sql  # embeddings <-> summaries <-> conversations
