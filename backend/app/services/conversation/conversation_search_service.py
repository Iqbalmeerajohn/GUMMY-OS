"""Conversation search service — keyword + semantic + hybrid ranking (M7).

Folds the message full-text hits and summary-embedding hits (from
``conversation_search_repository``) to conversation level, blends their scores, and
returns ranked, deep-linkable conversations. The Memory Engine and extraction
pipeline are untouched; this only reads conversation data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    CONVERSATION_SEARCH_KEYWORD_WEIGHT,
    CONVERSATION_SEARCH_SEMANTIC_WEIGHT,
    RETRIEVAL_CANDIDATE_MULTIPLIER,
)
from app.models.conversation import Conversation
from app.models.enums import ConversationSearchMode
from app.repositories import conversation_repository as conv_repo
from app.repositories import conversation_search_repository as search_repo
from app.services.embeddings.embedding_service import EmbeddingService


@dataclass(frozen=True)
class ConversationSearchHit:
    """A ranked conversation plus its blended/component scores + deep-link."""

    conversation: Conversation
    score: float
    keyword_score: float
    semantic_score: float
    match_message_id: uuid.UUID | None


def _fold_keyword(
    hits: list[tuple[uuid.UUID, uuid.UUID, float]],
) -> dict[uuid.UUID, tuple[float, uuid.UUID]]:
    """conversation_id → (best normalized rank, best-matching message_id)."""
    best: dict[uuid.UUID, tuple[float, uuid.UUID]] = {}
    for conversation_id, message_id, rank in hits:
        current = best.get(conversation_id)
        if current is None or rank > current[0]:
            best[conversation_id] = (rank, message_id)
    if not best:
        return {}
    max_rank = max(rank for rank, _ in best.values()) or 1.0
    return {
        cid: (rank / max_rank, msg_id) for cid, (rank, msg_id) in best.items()
    }


def _fold_semantic(
    hits: list[tuple[uuid.UUID, uuid.UUID, float]],
) -> dict[uuid.UUID, float]:
    """conversation_id → best similarity (1 - cosine_distance, clamped to [0,1])."""
    best: dict[uuid.UUID, float] = {}
    for conversation_id, _summary_id, distance in hits:
        similarity = max(0.0, min(1.0, 1.0 - distance))
        if conversation_id not in best or similarity > best[conversation_id]:
            best[conversation_id] = similarity
    return best


async def search(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    mode: ConversationSearchMode,
    limit: int,
    embedding_service: EmbeddingService,
) -> list[ConversationSearchHit]:
    """Search a user's conversations by keyword, semantic, or hybrid ranking."""
    candidate_limit = max(limit, limit * RETRIEVAL_CANDIDATE_MULTIPLIER)

    keyword_hits: list[tuple[uuid.UUID, uuid.UUID, float]] = []
    semantic_hits: list[tuple[uuid.UUID, uuid.UUID, float]] = []

    if mode in (ConversationSearchMode.KEYWORD, ConversationSearchMode.HYBRID):
        keyword_hits = await search_repo.keyword_search(
            session, user_id=user_id, query=query, limit=candidate_limit
        )
    if mode in (ConversationSearchMode.SEMANTIC, ConversationSearchMode.HYBRID):
        query_vector = await embedding_service.embed_query(query)
        semantic_hits = await search_repo.summary_semantic_search(
            session,
            user_id=user_id,
            query_vector=query_vector,
            embedding_model=embedding_service.model_name,
            limit=candidate_limit,
        )

    keyword = _fold_keyword(keyword_hits)
    semantic = _fold_semantic(semantic_hits)

    scored: list[tuple[uuid.UUID, float, float, float, uuid.UUID | None]] = []
    for conversation_id in keyword.keys() | semantic.keys():
        kw_score, message_id = keyword.get(conversation_id, (0.0, None))
        sem_score = semantic.get(conversation_id, 0.0)
        if mode is ConversationSearchMode.KEYWORD:
            score = kw_score
        elif mode is ConversationSearchMode.SEMANTIC:
            score = sem_score
        else:
            score = (
                CONVERSATION_SEARCH_KEYWORD_WEIGHT * kw_score
                + CONVERSATION_SEARCH_SEMANTIC_WEIGHT * sem_score
            )
        scored.append((conversation_id, score, kw_score, sem_score, message_id))

    scored.sort(key=lambda row: row[1], reverse=True)

    hits: list[ConversationSearchHit] = []
    for conversation_id, score, kw_score, sem_score, message_id in scored:
        if len(hits) >= limit:
            break
        # Re-fetch tenant-scoped + non-deleted (and skips any since-deleted thread).
        conversation = await conv_repo.get_conversation(
            session, conversation_id=conversation_id, user_id=user_id
        )
        if conversation is None:
            continue
        hits.append(
            ConversationSearchHit(
                conversation=conversation,
                score=score,
                keyword_score=kw_score,
                semantic_score=sem_score,
                match_message_id=message_id,
            )
        )
    return hits
