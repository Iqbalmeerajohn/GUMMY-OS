"""Embedding a file's chunks — the step that makes a document searchable.

Chunks have existed since M6 and were always described as "the reusable
substrate for future RAG". Nothing ever embedded them, so document search was a
substring match. This is that missing step, and it deliberately reuses the same
:class:`~app.services.embeddings.embedding_service.EmbeddingService` that
memories use — one embedding provider for the whole system, so a chunk vector
and a memory vector are always comparable and a model change moves both.

Two properties matter more than speed:

* **A failure is a failure.** If embedding raises, this raises, and the caller
  marks the file ``failed``. A file reported ``completed`` but never embedded is
  invisible to every search the user runs, and they find out by asking a
  question and being told nothing was found.
* **Re-indexing is idempotent.** Embedding an already-embedded file recomputes
  and overwrites. Chunking is deterministic, so the same bytes produce the same
  chunks and the same vectors; nothing accumulates.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file_chunk import FileChunk
from app.observability import langfuse as langfuse_obs
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.factory import get_embedding_service

logger = logging.getLogger(__name__)

# Chunks embedded per provider round trip. Ollama handles one text per call, so
# this bounds how much sits in memory rather than how many requests are made;
# large enough to keep the loop tight, small enough that a 500-page PDF does not
# hold every vector at once.
EMBED_BATCH_SIZE = 16


async def embed_file_chunks(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    file_id: uuid.UUID,
    embedding_service: EmbeddingService | None = None,
) -> int:
    """Embed every chunk of one file. Returns how many were embedded.

    Tenant-scoped by ``user_id`` in the query itself, not merely by the caller
    having checked ownership first — this runs on the shared session and a
    missing filter here would be a cross-tenant write.
    """
    service = embedding_service or get_embedding_service()
    stmt = (
        select(FileChunk)
        .where(FileChunk.user_id == user_id, FileChunk.file_id == file_id)
        .order_by(FileChunk.chunk_index)
    )
    chunks = list((await session.execute(stmt)).scalars().all())
    if not chunks:
        return 0

    model = service.model_name
    with langfuse_obs.observe_operation(
        "file.embed",
        metadata={"file_id": str(file_id), "chunks": len(chunks), "model": model},
    ) as span:
        embedded = 0
        for start in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[start : start + EMBED_BATCH_SIZE]
            for chunk in batch:
                # Deliberately not caught: the caller turns an exception into a
                # `failed` file. Swallowing it here would produce a document
                # that looks ready and can never be found.
                chunk.embedding = await service.embed_query(chunk.content)
                chunk.embedding_model = model
                embedded += 1
            await session.flush()
        span.update(metadata={"embedded": embedded})

    logger.info("embedded %d chunk(s) for file %s using %s", embedded, file_id, model)
    return embedded
