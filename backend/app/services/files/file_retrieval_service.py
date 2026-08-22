"""FileRetrievalService — read access to files and their chunks (M6).

The read seam future RAG, agents, and the workspace build on. It exposes file
metadata, paginated chunk retrieval, and keyword chunk search — **no vector
search yet** (that lands with the RAG layer). Read-only; it never mutates state,
so it takes the repositories directly and owns no unit of work.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_SEARCH_LIMIT, MAX_SEARCH_LIMIT
from app.models.file import File
from app.models.file_chunk import FileChunk
from app.observability import langfuse as langfuse_obs
from app.repositories import file_chunk_repository as chunk_repo
from app.services.embeddings.factory import get_embedding_service
from app.services.files import hybrid_retrieval
from app.services.files.file_service import get_file

logger = logging.getLogger(__name__)


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

    async def hybrid_search(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        query: str,
        file_id: uuid.UUID | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[hybrid_retrieval.RetrievedChunk]:
        """Vector + full-text retrieval with a relevance gate (RAG 2.0).

        The embedding failing must not take document search with it, so a
        provider error degrades to the lexical half rather than raising: the
        user still gets the chunks that literally contain their words.
        """
        bounded = max(1, min(limit, MAX_SEARCH_LIMIT))
        query_vector: list[float] | None = None
        try:
            query_vector = await get_embedding_service().embed_query(query)
        except Exception:
            logger.warning("query embedding failed; falling back to full-text only")
        return await hybrid_retrieval.search(
            session,
            user_id=user_id,
            query=query,
            query_vector=query_vector,
            limit=bounded,
            file_id=file_id,
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
