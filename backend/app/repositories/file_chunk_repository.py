"""Data-access layer for file chunks (persistence only, no commit).

Chunks are immutable once written (append-only). Search here is keyword-only
(``ILIKE`` substring) — vector search is deliberately out of scope for M6 and
lands with the future RAG layer.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.file_chunk import FileChunk


async def bulk_create_chunks(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    file_id: uuid.UUID,
    chunks: Iterable[dict],
) -> int:
    """Insert many chunks for a file. Returns the number created.

    Each ``chunks`` item must carry ``chunk_index``, ``content``,
    ``token_count``, and optional ``metadata_json``. Caller owns the commit.
    """
    rows = [
        FileChunk(
            user_id=user_id,
            file_id=file_id,
            chunk_index=c["chunk_index"],
            content=c["content"],
            token_count=c["token_count"],
            metadata_json=c.get("metadata_json"),
        )
        for c in chunks
    ]
    session.add_all(rows)
    await session.flush()
    return len(rows)


async def list_for_file(
    session: AsyncSession,
    *,
    file_id: uuid.UUID,
    user_id: uuid.UUID,
    limit: int,
    offset: int,
) -> tuple[list[FileChunk], int]:
    """Return a page of a file's chunks (in chunk order) and the total."""
    filters = (FileChunk.file_id == file_id, FileChunk.user_id == user_id)
    total = await session.scalar(
        select(func.count()).select_from(FileChunk).where(*filters)
    )
    stmt = (
        select(FileChunk)
        .where(*filters)
        .order_by(FileChunk.chunk_index)
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), int(total or 0)


async def search_chunks(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    file_id: uuid.UUID | None = None,
    limit: int,
) -> list[FileChunk]:
    """Keyword (substring) search over chunk content, newest file first.

    Scoped to one file when ``file_id`` is given, else across all the tenant's
    files. Preparation for RAG — no vector ranking yet.
    """
    filters = [FileChunk.user_id == user_id, FileChunk.content.ilike(f"%{query}%")]
    if file_id is not None:
        filters.append(FileChunk.file_id == file_id)
    stmt = (
        select(FileChunk)
        .where(*filters)
        .order_by(FileChunk.file_id, FileChunk.chunk_index)
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def search_chunks_by_terms(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    terms: list[str],
    file_ids: list[uuid.UUID] | None = None,
    candidate_limit: int,
) -> list[FileChunk]:
    """Fetch chunks matching ANY of ``terms`` (OR of ILIKEs), for re-ranking.

    Returns up to ``candidate_limit`` candidate chunks; the caller ranks them by
    how many distinct terms each contains (done in Python so ranking stays
    DB-portable — no full-text index needed for the M6.5 keyword retriever).
    ``file_ids`` optionally scopes the search to specific files.
    """
    if not terms:
        return []
    term_filter = or_(*(FileChunk.content.ilike(f"%{t}%") for t in terms))
    filters = [FileChunk.user_id == user_id, term_filter]
    if file_ids:
        filters.append(FileChunk.file_id.in_(file_ids))
    stmt = (
        select(FileChunk)
        # Eager-load the parent file so the service can read its filename
        # without an async lazy-load (which would raise MissingGreenlet).
        .options(selectinload(FileChunk.file))
        .where(*filters)
        .order_by(FileChunk.file_id, FileChunk.chunk_index)
        .limit(candidate_limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def delete_for_file(
    session: AsyncSession,
    *,
    file_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Delete all chunks for a file (used on reprocess). Caller commits."""
    await session.execute(
        delete(FileChunk).where(
            FileChunk.file_id == file_id,
            FileChunk.user_id == user_id,
        )
    )
    await session.flush()
