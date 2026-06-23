"""FileRetrievalService — read access to files and their chunks (M6).

The read seam future RAG, agents, and the workspace build on. It exposes file
metadata, paginated chunk retrieval, and keyword chunk search — **no vector
search yet** (that lands with the RAG layer). Read-only; it never mutates state,
so it takes the repositories directly and owns no unit of work.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_SEARCH_LIMIT, MAX_SEARCH_LIMIT
from app.models.file import File
from app.models.file_chunk import FileChunk
from app.observability import langfuse as langfuse_obs
from app.repositories import file_chunk_repository as chunk_repo
from app.services.files.file_service import get_file


class FileRetrievalService:
    """Read access over files and chunks (preparation for RAG)."""

    async def get_file_metadata(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        file_id: uuid.UUID,
    ) -> File:
        """Return one file's metadata or raise 404."""
        return await get_file(session, user_id=user_id, file_id=file_id)

    async def get_chunks(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        file_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[FileChunk], int]:
        """Return a page of a file's chunks (in order), raising 404 if missing.

        Validates ownership first (via :func:`get_file`) so chunk reads can
        never leak across tenants even before RLS.
        """
        await get_file(session, user_id=user_id, file_id=file_id)
        return await chunk_repo.list_for_file(
            session,
            file_id=file_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    async def search_chunks(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        query: str,
        file_id: uuid.UUID | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[FileChunk]:
        """Keyword search over chunk content (RAG prep; no vector ranking)."""
        bounded = max(1, min(limit, MAX_SEARCH_LIMIT))
        with langfuse_obs.observe_retrieval(
            "file.search_chunks",
            input=query,
            metadata={
                "file_id": str(file_id) if file_id else None,
                "limit": bounded,
            },
        ) as span:
            results = await chunk_repo.search_chunks(
                session,
                user_id=user_id,
                query=query,
                file_id=file_id,
                limit=bounded,
            )
            span.update(metadata={"results": len(results)})
        return results


# Module-level singleton (stateless; mirrors the other service seams).
file_retrieval_service = FileRetrievalService()
