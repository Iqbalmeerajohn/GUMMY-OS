"""Conversation search queries (Phase 2, M7).

Two tenant-scoped, PostgreSQL-only searches over a user's (non-deleted)
conversations:

  * keyword  — full-text over ``messages.content`` (GIN index from 0007), ranked
    by ``ts_rank``.
  * semantic — pgvector cosine over ``conversation_summary_embeddings`` (HNSW from
    0008), mirroring ``search_repository``.

Each ``build_*`` helper is pure (compile-tested against the PostgreSQL dialect with
no DB); the ``*_search`` functions execute. Hybrid ranking lives in the service.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.conversation_summary import ConversationSummary
from app.models.conversation_summary_embedding import (
    ConversationSummaryEmbedding,
)
from app.models.message import Message

_FTS_CONFIG = "english"


def build_keyword_statement(
    *,
    user_id: uuid.UUID,
    query: str,
    limit: int,
) -> Select[Any]:
    """Tenant-scoped full-text statement over messages, ranked by ts_rank.

    Returns rows of ``(conversation_id, message_id, rank)`` — one per matching
    message, best first. The service folds these to conversation level.
    """
    ts_vector = func.to_tsvector(_FTS_CONFIG, Message.content)
    ts_query = func.plainto_tsquery(_FTS_CONFIG, query)
    rank = func.ts_rank(ts_vector, ts_query).label("rank")

    return (
        select(Message.conversation_id, Message.id.label("message_id"), rank)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.user_id == user_id,
            Conversation.deleted_at.is_(None),
            ts_vector.op("@@")(ts_query),
        )
        .order_by(rank.desc())
        .limit(limit)
    )


def build_message_search_statement(
    *,
    user_id: uuid.UUID,
    query: str,
    limit: int,
) -> Select[Any]:
    """Tenant-scoped full-text statement returning the matching *messages*.

    Mirrors ``build_keyword_statement`` (same proven ``to_tsvector @@
    plainto_tsquery`` + ``ts_rank`` path) but keeps each message row and its
    content + parent conversation title, so unified search can render and
    highlight message snippets rather than folding to thread level.

    Returns rows of ``(message_id, conversation_id, role, content, title, rank)``,
    best first.
    """
    ts_vector = func.to_tsvector(_FTS_CONFIG, Message.content)
    ts_query = func.plainto_tsquery(_FTS_CONFIG, query)
    rank = func.ts_rank(ts_vector, ts_query).label("rank")

    return (
        select(
            Message.id.label("message_id"),
            Message.conversation_id,
            Message.role,
            Message.content,
            Conversation.title,
            rank,
        )
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.user_id == user_id,
            Conversation.deleted_at.is_(None),
            ts_vector.op("@@")(ts_query),
        )
        .order_by(rank.desc())
        .limit(limit)
    )


def build_summary_semantic_statement(
    *,
    user_id: uuid.UUID,
    query_vector: list[float],
    embedding_model: str,
    limit: int,
) -> Select[Any]:
    """Tenant-scoped cosine-similarity statement over summary embeddings.

    Returns rows of ``(conversation_id, summary_id, distance)``, nearest first.
    """
    embedding_col: Any = ConversationSummaryEmbedding.embedding_vector
    distance = embedding_col.cosine_distance(query_vector).label("distance")

    return (
        select(
            ConversationSummary.conversation_id,
            ConversationSummaryEmbedding.summary_id,
            distance,
        )
        .join(
            ConversationSummary,
            ConversationSummary.id == ConversationSummaryEmbedding.summary_id,
        )
        .join(
            Conversation,
            Conversation.id == ConversationSummary.conversation_id,
        )
        .where(
            ConversationSummaryEmbedding.user_id == user_id,
            Conversation.deleted_at.is_(None),
            ConversationSummaryEmbedding.embedding_model == embedding_model,
        )
        .order_by(distance)
        .limit(limit)
    )


async def keyword_search(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    limit: int,
) -> list[tuple[uuid.UUID, uuid.UUID, float]]:
    """Execute the keyword statement → ``(conversation_id, message_id, rank)``."""
    stmt = build_keyword_statement(user_id=user_id, query=query, limit=limit)
    result = await session.execute(stmt)
    return [(row[0], row[1], float(row[2])) for row in result.all()]


async def message_search(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    limit: int,
) -> list[tuple[uuid.UUID, uuid.UUID, Any, str, str | None, float]]:
    """Execute the message statement.

    → ``(message_id, conversation_id, role, content, title, rank)``.
    """
    stmt = build_message_search_statement(
        user_id=user_id, query=query, limit=limit
    )
    result = await session.execute(stmt)
    return [
        (row[0], row[1], row[2], row[3], row[4], float(row[5]))
        for row in result.all()
    ]


async def summary_semantic_search(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query_vector: list[float],
    embedding_model: str,
    limit: int,
) -> list[tuple[uuid.UUID, uuid.UUID, float]]:
    """Execute the semantic statement → ``(conversation_id, summary_id, dist)``."""
    stmt = build_summary_semantic_statement(
        user_id=user_id,
        query_vector=query_vector,
        embedding_model=embedding_model,
        limit=limit,
    )
    result = await session.execute(stmt)
    return [(row[0], row[1], float(row[2])) for row in result.all()]
