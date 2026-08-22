"""File endpoints (``/api/v1/files``) — thin HTTP over the files services (M6).

Upload (multipart), list, get, list chunks, file stats, and delete. Every route
is tenant-scoped via ``CurrentUserId`` and ownership-checked in the service
layer (foreign tenants see 404, never 403).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile, status

from app.api.deps import CurrentUserId, DbSession
from app.core.constants import (
    CONTEXT_MAX_FILES,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
)
from app.repositories import file_repository
from app.schemas.file import (
    FileChunkListResponse,
    FileChunkResponse,
    FileListResponse,
    FileResponse,
    FileStatsResponse,
)
from app.services.files import file_service
from app.services.files.file_retrieval_service import file_retrieval_service

router = APIRouter(prefix="/files", tags=["files"])


@router.post(
    "/upload",
    response_model=FileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file (multipart)",
)
async def upload_file(
    user_id: CurrentUserId,
    db: DbSession,
    file: Annotated[UploadFile, File(description="The file to upload.")],
) -> FileResponse:
    data = await file.read()
    created = await file_service.upload_file(
        db,
        user_id=user_id,
        original_filename=file.filename or "upload",
        content_type=file.content_type,
        data=data,
    )
    return FileResponse.model_validate(created)


@router.get("", response_model=FileListResponse, summary="List files")
async def list_files(
    user_id: CurrentUserId,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FileListResponse:
    items, total = await file_service.list_files(
        db, user_id=user_id, limit=limit, offset=offset
    )
    return FileListResponse(
        items=[FileResponse.model_validate(f) for f in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/stats",
    response_model=FileStatsResponse,
    summary="Aggregate file counts + recent files for the dashboard",
)
async def file_stats(
    user_id: CurrentUserId,
    db: DbSession,
) -> FileStatsResponse:
    total = await file_repository.count_files(db, user_id=user_id)
    recent = await file_repository.list_recent(
        db, user_id=user_id, limit=CONTEXT_MAX_FILES
    )
    return FileStatsResponse(
        total=total,
        recent=[FileResponse.model_validate(f) for f in recent],
    )


@router.get("/{file_id}", response_model=FileResponse, summary="Get a file by id")
async def get_file(
    file_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> FileResponse:
    file = await file_service.get_file(db, user_id=user_id, file_id=file_id)
    return FileResponse.model_validate(file)


@router.get(
    "/{file_id}/chunks",
    response_model=FileChunkListResponse,
    summary="List a file's text chunks (RAG preparation)",
)
async def list_file_chunks(
    file_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FileChunkListResponse:
    items, total = await file_retrieval_service.get_chunks(
        db,
        user_id=user_id,
        file_id=file_id,
        limit=limit,
        offset=offset,
    )
    return FileChunkListResponse(
        items=[FileChunkResponse.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{file_id}/reindex",
    response_model=FileResponse,
    summary="Re-extract, re-chunk and re-embed a file",
)
async def reindex_file(
    file_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
) -> FileResponse:
    """Rebuild a file's searchable knowledge from the bytes already stored.

    The way back from a failed extraction, and how an improved extractor or a
    changed embedding model reaches documents that were uploaded before it.
    """
    file = await file_service.reindex_file(session, user_id=user_id, file_id=file_id)
    return FileResponse.model_validate(file)


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a file and its chunks",
)
async def delete_file(
    file_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> None:
    await file_service.delete_file(db, user_id=user_id, file_id=file_id)
