"""Unified Knowledge & Retrieval Engine endpoints (``/api/v1/knowledge``).

Thin HTTP layer over the M7 engine. The diagnostics endpoint traces a query
through the full pipeline — retrieval (memories + goals + files) → cross-source
ranking → compression — and returns exactly what would be packed into the
prompt's ``<knowledge>`` block, so retrieval issues can be debugged the same way
``/memories/diagnostics`` debugs memory recall.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserId, DbSession, EmbeddingServiceDep
from app.core.exceptions import AppError
from app.schemas.knowledge import (
    KnowledgeDiagnosticItem,
    KnowledgeDiagnosticsResponse,
)
from app.services.knowledge import (
    knowledge_context_builder,
    knowledge_ranker,
    knowledge_retrieval_service,
)
from app.services.knowledge.knowledge_context_builder import item_key

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# Cap the content shown per item in the diagnostics payload (full text lives in
# the prompt block); keeps the response lean.
_DIAGNOSTIC_CONTENT_CAP = 280


@router.get(
    "/diagnostics",
    response_model=KnowledgeDiagnosticsResponse,
    summary="Trace a query through the unified knowledge pipeline",
)
async def knowledge_diagnostics(
    user_id: CurrentUserId,
    db: DbSession,
    embeddings: EmbeddingServiceDep,
    q: Annotated[str, Query(min_length=1, max_length=1000)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> KnowledgeDiagnosticsResponse:
    """Retrieve → rank → compress a query and report every step.

    Surfaces what was retrieved from each source, the fused cross-source ranking
    (each item tagged with its origin), and which items survive compression into
    the prompt's ``<knowledge>`` block. Read-only — reinforcement is disabled so
    inspecting recall never mutates memory scores.
    """
    query = q.strip()
    if not query:
        raise AppError(
            "query must not be empty or whitespace",
            code="empty_query",
            status_code=422,
        )

    ctx = await knowledge_retrieval_service.retrieve(
        db,
        user_id=user_id,
        query=query,
        embedding_service=embeddings,
        reinforce=False,
    )
    ranked = knowledge_ranker.rank(ctx)
    compiled = knowledge_context_builder.build(ranked, inventory=ctx.inventory)

    items = [
        KnowledgeDiagnosticItem(
            source=item.source,
            label=item.label,
            content=item.content[:_DIAGNOSTIC_CONTENT_CAP],
            source_score=round(item.source_score, 4),
            rank_score=round(item.rank_score, 4),
            included_in_prompt=item_key(item) in compiled.included_keys,
        )
        for item in ranked[:limit]
    ]

    return KnowledgeDiagnosticsResponse(
        query=query,
        memories_used=len(ctx.memories),
        goals_used=len(ctx.goals),
        files_used=len(ctx.files),
        sources_used=ctx.sources_used,
        ranked_items=items,
        token_estimate=compiled.token_estimate,
        knowledge_block=compiled.block,
    )
