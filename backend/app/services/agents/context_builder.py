"""Agent Context Builder — assemble the token-budgeted pack an agent gets.

A composition layer over the Phase 1/2 machinery: hybrid memory retrieval
(`memory_retrieval_service`) for ranked candidates, with thread history and
the rolling summary supplied by the caller (`run_turn` loads them *before*
appending the current user message, so the query never leaks into history —
the Phase 2 ordering preserved exactly). Token budgeting/dedupe stay in
`context_assembly_service`, applied by the handler at prompt time
(PHASE3_PLAN.md §8).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_CONTEXT_MAX_MEMORIES
from app.schemas.agents import ContextPack
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.memory import memory_retrieval_service


async def build(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    embedding_service: EmbeddingService,
    max_memories: int = DEFAULT_CONTEXT_MAX_MEMORIES,
    history: list[dict] | None = None,
    summary: str | None = None,
    scratch: list[dict] | None = None,
) -> ContextPack:
    """Build a scoped context pack for one agent dispatch.

    ``memories`` are the ranked retrieval candidates (content/category/score),
    exactly what the Phase 2 core feeds into context assembly. ``goals`` and
    ``tasks`` stay empty until M8 wires the Goal & Task Foundation.
    """
    ranked = await memory_retrieval_service.retrieve_memories(
        session,
        user_id=user_id,
        query=query,
        embedding_service=embedding_service,
        limit=max_memories,
    )
    memories = [
        {
            "content": item.memory.content,
            "category": item.memory.category.value,
            "score": item.final_score,
        }
        for item in ranked
    ]
    return ContextPack(
        memories=memories,
        history=list(history or []),
        summary=summary,
        scratch=list(scratch or []),
    )
