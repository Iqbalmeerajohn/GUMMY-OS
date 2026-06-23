"""Data-access layer for files (persistence only, no commit).

Ordering is newest-first (most recently uploaded surfaces at the top of the
Files page, the dashboard widget, and agent context).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProcessingStatus, UploadStatus
from app.models.file import File


async def create_file(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    filename: str,
    original_filename: str,
    mime_type: str,
    size_bytes: int,
    storage_path: str | None = None,
    upload_status: UploadStatus = UploadStatus.PENDING,
    processing_status: ProcessingStatus = ProcessingStatus.PENDING,
) -> File:
    """Insert a new file row and flush to populate id."""
    file = File(
        user_id=user_id,
        filename=filename,
        original_filename=original_filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        storage_path=storage_path,
        upload_status=upload_status,
        processing_status=processing_status,
    )
    session.add(file)
    await session.flush()
    return file


async def get_file(
    session: AsyncSession,
    *,
    file_id: uuid.UUID,
    user_id: uuid.UUID,
) -> File | None:
    """Fetch a single tenant-scoped file by id, if it exists."""
    stmt = select(File).where(File.id == file_id, File.user_id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_files(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
    offset: int,
) -> tuple[list[File], int]:
    """Return a page of files (newest first) and the total count."""
    total = await session.scalar(
        select(func.count()).select_from(File).where(File.user_id == user_id)
    )
    stmt = (
        select(File)
        .where(File.user_id == user_id)
        .order_by(File.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), int(total or 0)


async def list_recent(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
) -> list[File]:
    """Most recently uploaded files (for dashboard + agent context)."""
    stmt = (
        select(File)
        .where(File.user_id == user_id)
        .order_by(File.created_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def count_files(session: AsyncSession, *, user_id: uuid.UUID) -> int:
    """Total file count for a tenant (dashboard widget)."""
    total = await session.scalar(
        select(func.count()).select_from(File).where(File.user_id == user_id)
    )
    return int(total or 0)


async def delete_file(session: AsyncSession, *, file: File) -> None:
    """Delete a file and (cascade) its chunks. Caller owns the commit."""
    await session.delete(file)
    await session.flush()
