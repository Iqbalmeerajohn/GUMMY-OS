"""File Intelligence retrieval (M6.5) — turn a query (+ optional attachments)
into grounding file content for a conversation prompt.

Two modes, both tenant-scoped and traced to Langfuse:

* **attachment** — when the turn carries ``attached_file_ids``, use *only* those
  files' chunks (in order). The user pointed at specific documents; we never
  dilute that with a broad search. Ownership is enforced (foreign id → 404).
* **search** — otherwise, hybrid-retrieve the most relevant chunks across all
  the user's files: vector similarity fused with Postgres full-text, gated by a
  calibrated relevance floor (see ``hybrid_retrieval``). This is the seam M6.5
  left for RAG, now filled.

  The original keyword path is still here, as a fallback rather than a rival.
  Hybrid retrieval needs pgvector and ``websearch_to_tsquery``; the test suite
  runs on SQLite, and a provider or index outage should degrade document search
  rather than delete it. So a failure drops to ILIKE term matching, which finds
  strictly less but needs nothing but SQL.

The service also returns a lightweight **inventory** (recent files' metadata) so
the assistant can answer "what files do I have?" from the same context block.
Read-only; owns no unit of work.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    CONTEXT_MAX_FILES,
    FILE_CONTEXT_CANDIDATE_MULTIPLIER,
    FILE_CONTEXT_CHUNK_CHAR_CAP,
    FILE_CONTEXT_MAX_CHUNKS,
    FILE_SEARCH_MIN_TERM_LENGTH,
)
from app.observability import langfuse as langfuse_obs
from app.repositories import file_chunk_repository as chunk_repo
from app.repositories import file_repository as file_repo
from app.services.files.file_service import get_file

logger = logging.getLogger(__name__)

# A small stop-list so common question words don't drive keyword retrieval.
_STOPWORDS = frozenset(
    {
        "what",
        "whats",
        "which",
        "where",
        "when",
        "who",
        "whom",
        "how",
        "why",
        "the",
        "and",
        "for",
        "are",
        "was",
        "were",
        "you",
        "your",
        "yours",
        "this",
        "that",
        "these",
        "those",
        "with",
        "from",
        "about",
        "into",
        "have",
        "has",
        "had",
        "does",
        "did",
        "can",
        "could",
        "would",
        "should",
        "tell",
        "show",
        "give",
        "list",
        "find",
        "any",
        "all",
        "some",
        "please",
        "summarize",
        "summary",
        "explain",
        "describe",
        "mentioned",
        "document",
        "documents",
        "file",
        "files",
        "uploaded",
        "upload",
    }
)


@dataclass(frozen=True)
class FileExcerpt:
    """One chunk of file content selected as grounding for a reply."""

    file_id: uuid.UUID
    filename: str
    chunk_index: int
    content: str
    # How to cite this excerpt: "Resume.pdf — page 2" when extraction recorded
    # a location, otherwise just the filename. Never invented — see
    # RetrievedChunk.source_label.
    source_label: str = ""

    @property
    def citation(self) -> str:
        return self.source_label or self.filename


@dataclass(frozen=True)
class FileContext:
    """The file grounding for one turn: relevant excerpts + a file inventory."""

    # "attachment" | "search" | "none"
    mode: str
    excerpts: list[FileExcerpt] = field(default_factory=list)
    # Lightweight metadata of the user's files (for "what files do I have?").
    inventory: list[dict] = field(default_factory=list)
    file_ids: list[uuid.UUID] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.excerpts and not self.inventory


def extract_terms(query: str) -> list[str]:
    """Tokenize a query into distinct, meaningful lowercase search terms."""
    seen: list[str] = []
    for raw in re.findall(r"[A-Za-z0-9]+", query.lower()):
        if len(raw) < FILE_SEARCH_MIN_TERM_LENGTH or raw in _STOPWORDS:
            continue
        if raw not in seen:
            seen.append(raw)
    return seen


def _to_excerpt(chunk) -> FileExcerpt:  # type: ignore[no-untyped-def]
    filename = chunk.file.original_filename if chunk.file else str(chunk.file_id)
    return FileExcerpt(
        file_id=chunk.file_id,
        filename=filename,
        chunk_index=chunk.chunk_index,
        content=chunk.content[:FILE_CONTEXT_CHUNK_CHAR_CAP],
    )


async def _build_inventory(session: AsyncSession, *, user_id: uuid.UUID) -> list[dict]:
    """Recent files' metadata (filename / status / chunk count / uploaded)."""
    recent = await file_repo.list_recent(
        session, user_id=user_id, limit=CONTEXT_MAX_FILES
    )
    return [
        {
            "filename": f.original_filename,
            "processing_status": f.processing_status.value,
            "chunk_count": f.chunk_count,
            "uploaded_at": f.created_at.date().isoformat(),
        }
        for f in recent
    ]


async def _attachment_excerpts(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    attached_file_ids: list[uuid.UUID],
    max_chunks: int,
) -> list[FileExcerpt]:
    """All chunks of the attached files (ownership-checked), capped in order."""
    excerpts: list[FileExcerpt] = []
    for file_id in attached_file_ids:
        # Ownership enforced: a foreign/missing id raises 404 (safety contract).
        file = await get_file(session, user_id=user_id, file_id=file_id)
        chunks, _ = await chunk_repo.list_for_file(
            session,
            file_id=file_id,
            user_id=user_id,
            limit=max_chunks,
            offset=0,
        )
        for c in chunks:
            excerpts.append(
                FileExcerpt(
                    file_id=file.id,
                    filename=file.original_filename,
                    chunk_index=c.chunk_index,
                    content=c.content[:FILE_CONTEXT_CHUNK_CHAR_CAP],
                )
            )
            if len(excerpts) >= max_chunks:
                return excerpts
    return excerpts


async def _search_excerpts(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    max_chunks: int,
) -> list[FileExcerpt]:
    """Hybrid-retrieve grounding chunks, falling back to keyword matching.

    The fallback is deliberately silent to the caller: whether an answer was
    grounded by vectors or by ILIKE is our business, and both produce the same
    excerpts. What the caller must never see is an exception, because a document
    search outage would then take the whole conversation turn with it.
    """
    from app.services.files.file_retrieval_service import file_retrieval_service

    try:
        hits = await file_retrieval_service.hybrid_search(
            session, user_id=user_id, query=query, limit=max_chunks
        )
    except Exception:
        logger.warning(
            "hybrid file retrieval unavailable; falling back to keyword search",
            exc_info=True,
        )
    else:
        return [
            FileExcerpt(
                file_id=hit.chunk.file_id,
                filename=hit.filename,
                chunk_index=hit.chunk.chunk_index,
                content=hit.chunk.content[:FILE_CONTEXT_CHUNK_CHAR_CAP],
                source_label=hit.source_label,
            )
            for hit in hits
        ]
    return await _keyword_excerpts(
        session, user_id=user_id, query=query, max_chunks=max_chunks
    )


async def _keyword_excerpts(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    max_chunks: int,
) -> list[FileExcerpt]:
    """Keyword-retrieve the most relevant chunks, re-ranked by term coverage."""
    terms = extract_terms(query)
    if not terms:
        return []
    candidates = await chunk_repo.search_chunks_by_terms(
        session,
        user_id=user_id,
        terms=terms,
        candidate_limit=max_chunks * FILE_CONTEXT_CANDIDATE_MULTIPLIER,
    )

    # Rank by how many distinct terms each chunk contains (desc), stable by
    # file then chunk order. Portable across SQLite/Postgres (no FTS index).
    def _score(chunk) -> int:  # type: ignore[no-untyped-def]
        lowered = chunk.content.lower()
        return sum(1 for t in terms if t in lowered)

    ranked = sorted(candidates, key=_score, reverse=True)
    return [_to_excerpt(c) for c in ranked[:max_chunks]]


async def retrieve_file_context(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    attached_file_ids: list[uuid.UUID] | None = None,
    max_chunks: int = FILE_CONTEXT_MAX_CHUNKS,
    include_inventory: bool = True,
) -> FileContext:
    """Assemble file grounding for one turn (attachment-first, else search).

    Best-effort by default for the *search* path (a file-retrieval hiccup must
    never cost a reply) — but the *attachment* path propagates a 404 for a
    foreign/missing id, because the user explicitly referenced that file and a
    silent miss would be wrong (and is a tenancy signal).
    """
    if attached_file_ids:
        with langfuse_obs.observe_retrieval(
            "file.attachments",
            input=query,
            metadata={
                "attached_file_count": len(attached_file_ids),
                "max_chunks": max_chunks,
            },
        ) as span:
            excerpts = await _attachment_excerpts(
                session,
                user_id=user_id,
                attached_file_ids=attached_file_ids,
                max_chunks=max_chunks,
            )
            span.update(metadata={"excerpts": len(excerpts)})
        inventory = (
            await _build_inventory(session, user_id=user_id)
            if include_inventory
            else []
        )
        return FileContext(
            mode="attachment",
            excerpts=excerpts,
            inventory=inventory,
            file_ids=list(attached_file_ids),
        )

    with langfuse_obs.observe_retrieval(
        "file.search",
        input=query,
        metadata={"max_chunks": max_chunks},
    ) as span:
        excerpts = []
        try:
            excerpts = await _search_excerpts(
                session, user_id=user_id, query=query, max_chunks=max_chunks
            )
        except Exception:
            logger.exception("file search failed; replying without file context")
        span.update(metadata={"excerpts": len(excerpts)})

    inventory = []
    if include_inventory:
        try:
            inventory = await _build_inventory(session, user_id=user_id)
        except Exception:
            logger.exception("file inventory failed; omitting from context")

    return FileContext(
        mode="search" if excerpts else "none",
        excerpts=excerpts,
        inventory=inventory,
        file_ids=[e.file_id for e in excerpts],
    )


def render_file_context(ctx: FileContext) -> dict | None:
    """Shape a :class:`FileContext` for ``prompt_builder.build_prompt(files=...)``.

    Returns ``None`` when there is nothing to add (keeps the prompt
    byte-identical to the no-files path). Otherwise a dict with an ``inventory``
    list and an ``excerpts`` list of ``{filename, content}``.
    """
    if ctx.is_empty:
        return None
    return {
        "inventory": ctx.inventory,
        "excerpts": [
            {"filename": e.filename, "content": e.content} for e in ctx.excerpts
        ],
    }
