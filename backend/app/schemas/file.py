"""Pydantic schemas for files + chunks (the M6 wire contract)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProcessingStatus, UploadStatus


class FileResponse(BaseModel):
    """A file as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    original_filename: str
    mime_type: str
    size_bytes: int
    upload_status: UploadStatus
    processing_status: ProcessingStatus
    chunk_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class FileListResponse(BaseModel):
    """A paginated list of files."""

    items: list[FileResponse]
    total: int
    limit: int
    offset: int


class FileChunkResponse(BaseModel):
    """A single file chunk as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int
    metadata_json: dict | None
    created_at: datetime


class FileChunkListResponse(BaseModel):
    """A paginated list of a file's chunks."""

    items: list[FileChunkResponse]
    total: int
    limit: int
    offset: int


class FileStatsResponse(BaseModel):
    """Aggregate file counts for the dashboard widget."""

    total: int
    recent: list[FileResponse] = Field(default_factory=list)
