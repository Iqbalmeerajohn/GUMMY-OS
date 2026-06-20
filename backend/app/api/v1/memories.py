"""Memory CRUD endpoints (``/api/v1/memories``).

Thin HTTP layer: resolve the tenant + session, delegate to the memory service,
and shape the response. No business logic here.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import (
    CurrentUserId,
    DbSession,
    EmbeddingServiceDep,
    SettingsDep,
)
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.core.exceptions import AppError
from app.models.enums import MemoryCategory, MemoryStatus
from app.repositories import search_repository as search_repo
from app.schemas.diagnostics import DiagnosticMemory, MemoryDiagnosticsResponse
from app.schemas.memory import (
    MemoryCreate,
    MemoryListResponse,
    MemoryResponse,
    MemoryUpdate,
)
from app.schemas.retrieval import (
    MemoryRetrievalRequest,
    MemoryRetrievalResponse,
    RetrievedMemory,
)
from app.schemas.search import (
    MemoryEmbeddingResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySearchResult,
)
from app.services.memory import (
    context_assembly_service,
    memory_retrieval_service,
    memory_service,
)
from app.services.memory.context_assembly_service import (
    ContextMemory,
    render_memory_line,
)

router = APIRouter(prefix="/memories", tags=["memories"])


@router.post(
    "",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a memory",
)
async def create_memory(
    payload: MemoryCreate,
    user_id: CurrentUserId,
    db: DbSession,
) -> MemoryResponse:
    memory = await memory_service.create_memory(db, user_id=user_id, payload=payload)
    return MemoryResponse.model_validate(memory)


@router.get(
    "",
    response_model=MemoryListResponse,
    summary="List memories",
)
async def list_memories(
    user_id: CurrentUserId,
    db: DbSession,
    category: MemoryCategory | None = None,
    status: MemoryStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MemoryListResponse:
    items, total = await memory_service.list_memories(
        db,
        user_id=user_id,
        category=category,
        status=status,
        limit=limit,
        offset=offset,
    )
    return MemoryListResponse(
        items=[MemoryResponse.model_validate(m) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/diagnostics",
    response_model=MemoryDiagnosticsResponse,
    summary="Memory-confidence diagnostics: trace a fact through the pipeline",
)
async def memory_diagnostics(
    user_id: CurrentUserId,
    db: DbSession,
    embeddings: EmbeddingServiceDep,
    settings: SettingsDep,
    q: Annotated[str, Query(min_length=1, max_length=1000)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> MemoryDiagnosticsResponse:
    """Trace a query through retrieval → ranking → prompt selection.

    Surfaces the four things that decide whether a remembered fact reaches the
    model: whether extraction is even on (``consent_mode``), what is stored,
    each candidate's retrieval scores, and which candidates survive token-budget
    selection into the prompt's ``<memory>`` block. Read-only (no reinforcement).
    """
    query = q.strip()
    if not query:
        raise AppError(
            "query must not be empty or whitespace",
            code="empty_query",
            status_code=422,
        )

    consent = settings.memory_consent_mode.lower()
    _, total = await memory_service.list_memories(
        db, user_id=user_id, category=None, status=None, limit=1, offset=0
    )

    ranked = await memory_retrieval_service.retrieve_memories(
        db,
        user_id=user_id,
        query=query,
        embedding_service=embeddings,
        limit=limit,
        reinforce=False,
    )
    candidates = [
        ContextMemory(
            content=item.memory.content,
            category=item.memory.category.value,
            score=item.final_score,
        )
        for item in ranked
    ]
    package = context_assembly_service.assemble_context(candidates)
    included = {m.content.strip().lower() for m in package.memories}

    results = [
        DiagnosticMemory(
            id=item.memory.id,
            category=item.memory.category,
            content=item.memory.content,
            importance_score=item.memory.importance_score,
            confidence_score=item.memory.confidence_score,
            semantic_similarity=item.semantic_similarity,
            recency_score=item.recency_score,
            final_score=item.final_score,
            included_in_prompt=item.memory.content.strip().lower() in included,
        )
        for item in ranked
    ]
    prompt_block = (
        "\n".join(render_memory_line(m) for m in package.memories)
        or "(no memories selected)"
    )

    return MemoryDiagnosticsResponse(
        query=query,
        consent_mode=consent,
        extraction_enabled=consent == "autonomous",
        total_memories=total,
        retrieved_count=len(results),
        included_count=len(package.memories),
        results=results,
        prompt_memory_block=prompt_block,
    )


@router.get(
    "/{memory_id}",
    response_model=MemoryResponse,
    summary="Get a memory by id",
)
async def get_memory(
    memory_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> MemoryResponse:
    memory = await memory_service.get_memory(db, user_id=user_id, memory_id=memory_id)
    return MemoryResponse.model_validate(memory)


@router.patch(
    "/{memory_id}",
    response_model=MemoryResponse,
    summary="Update a memory",
)
async def update_memory(
    memory_id: uuid.UUID,
    payload: MemoryUpdate,
    user_id: CurrentUserId,
    db: DbSession,
) -> MemoryResponse:
    memory = await memory_service.update_memory(
        db, user_id=user_id, memory_id=memory_id, payload=payload
    )
    return MemoryResponse.model_validate(memory)


@router.post(
    "/{memory_id}/archive",
    response_model=MemoryResponse,
    summary="Archive a memory",
)
async def archive_memory(
    memory_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> MemoryResponse:
    memory = await memory_service.archive_memory(
        db, user_id=user_id, memory_id=memory_id
    )
    return MemoryResponse.model_validate(memory)


@router.post(
    "/{memory_id}/restore",
    response_model=MemoryResponse,
    summary="Restore (un-archive) a memory",
)
async def restore_memory(
    memory_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> MemoryResponse:
    memory = await memory_service.restore_memory(
        db, user_id=user_id, memory_id=memory_id
    )
    return MemoryResponse.model_validate(memory)


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a memory",
)
async def delete_memory(
    memory_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> None:
    await memory_service.delete_memory(db, user_id=user_id, memory_id=memory_id)


@router.post(
    "/search",
    response_model=MemorySearchResponse,
    summary="Semantic search over memories",
)
async def search_memories(
    payload: MemorySearchRequest,
    user_id: CurrentUserId,
    db: DbSession,
    embeddings: EmbeddingServiceDep,
) -> MemorySearchResponse:
    query_vector = await embeddings.embed_query(payload.query)
    rows = await search_repo.search_similar_memories(
        db,
        user_id=user_id,
        query_vector=query_vector,
        embedding_model=embeddings.model_name,
        limit=payload.limit,
        include_archived=payload.include_archived,
        category=payload.category,
    )
    results = [
        MemorySearchResult(
            id=memory.id,
            user_id=memory.user_id,
            category=memory.category,
            content=memory.content,
            importance_score=memory.importance_score,
            confidence_score=memory.confidence_score,
            status=memory.status,
            similarity_score=1.0 - distance,
            created_at=memory.created_at,
            updated_at=memory.updated_at,
        )
        for memory, distance in rows
    ]
    return MemorySearchResponse(
        query=payload.query,
        count=len(results),
        results=results,
    )


@router.post(
    "/retrieve",
    response_model=MemoryRetrievalResponse,
    summary="Hybrid retrieval (semantic + importance + confidence + recency)",
)
async def retrieve_memories(
    payload: MemoryRetrievalRequest,
    user_id: CurrentUserId,
    db: DbSession,
    embeddings: EmbeddingServiceDep,
) -> MemoryRetrievalResponse:
    ranked = await memory_retrieval_service.retrieve_memories(
        db,
        user_id=user_id,
        query=payload.query,
        embedding_service=embeddings,
        limit=payload.limit,
        category=payload.category,
        include_archived=payload.include_archived,
        reinforce=payload.reinforce,
    )
    results = [
        RetrievedMemory(
            id=item.memory.id,
            user_id=item.memory.user_id,
            category=item.memory.category,
            content=item.memory.content,
            importance_score=item.memory.importance_score,
            confidence_score=item.memory.confidence_score,
            status=item.memory.status,
            recall_count=item.memory.recall_count,
            semantic_similarity=item.semantic_similarity,
            recency_score=item.recency_score,
            final_score=item.final_score,
            created_at=item.memory.created_at,
            updated_at=item.memory.updated_at,
        )
        for item in ranked
    ]
    return MemoryRetrievalResponse(
        query=payload.query,
        count=len(results),
        results=results,
    )


@router.post(
    "/{memory_id}/embed",
    response_model=MemoryEmbeddingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate or refresh a memory's embedding",
)
async def embed_memory(
    memory_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
    embeddings: EmbeddingServiceDep,
) -> MemoryEmbeddingResponse:
    memory = await memory_service.get_memory(db, user_id=user_id, memory_id=memory_id)
    embedding = await embeddings.sync_memory_embedding(db, memory=memory)
    await db.commit()
    await db.refresh(embedding)
    return MemoryEmbeddingResponse.model_validate(embedding)
