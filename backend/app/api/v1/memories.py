"""Memory CRUD endpoints (``/api/v1/memories``).

Thin HTTP layer: resolve the tenant + session, delegate to the memory service,
and shape the response. No business logic here.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserId, DbSession
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.models.enums import MemoryCategory, MemoryStatus
from app.schemas.memory import (
    MemoryCreate,
    MemoryListResponse,
    MemoryResponse,
    MemoryUpdate,
)
from app.services.memory import memory_service

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
