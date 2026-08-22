"""Hybrid retrieval over document chunks: vectors plus full text.

    query → normalize → (vector ∥ full-text) → merge → dedupe → rank → gate

Neither signal is sufficient alone, which is why both run.

Vector search finds passages that *mean* the same thing as the question and is
the only way "what did I study?" reaches a chunk that says "coursework". It is
also reliably bad at exact tokens: a surname, ``BiLSTM``, a column header, a
version string — an embedding smears those into a neighbourhood of similar
strings, so the chunk that literally contains the word is often not first.

Postgres full-text is the mirror image: exact on terms, blind to paraphrase.

The merge is Reciprocal Rank Fusion. It combines *rank positions* rather than
scores, which matters because a cosine similarity and a ``ts_rank`` are not
comparable quantities — normalising them against each other would invent a
relationship that does not exist. RRF only asks "how near the top did each
retriever put this?", which is a fair question to ask of both.

The gate is the part that keeps documents out of answers they have nothing to
do with. Top-N alone always returns N results; asked "what is the capital of
France?", a library of one resume returns that resume. A floor on the *raw*
semantic similarity — not on the blended score — is what makes "nothing here is
relevant" an expressible outcome.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import Float, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    FILE_RETRIEVAL_CANDIDATES,
    FILE_RETRIEVAL_MIN_SIMILARITY,
    FILE_RETRIEVAL_RRF_K,
)
from app.models.file import File
from app.models.file_chunk import FileChunk
from app.observability import langfuse as langfuse_obs

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievedChunk:
    """One chunk that survived ranking, with everything needed to cite it."""

    chunk: FileChunk
    filename: str
    similarity: float
    score: float
    matched_vector: bool
    matched_text: bool

    @property
    def source_label(self) -> str:
        """Human source, e.g. ``Resume.pdf — page 2``.

        Built from what extraction actually recorded, so it can never claim a
        page the chunk does not have.
        """
        meta = self.chunk.metadata_json or {}
        page = meta.get("page")
        section = meta.get("section")
        row_start, row_end = meta.get("row_start"), meta.get("row_end")
        if page is not None:
            return f"{self.filename} — page {page}"
        if section:
            return f"{self.filename} — {section}"
        if row_start is not None and row_end is not None:
            return f"{self.filename} — rows {row_start}–{row_end}"
        return self.filename


def normalize_query(query: str) -> str:
    """Collapse whitespace and drop characters that only confuse tsquery."""
    return re.sub(r"\s+", " ", query).strip()


def _to_tsquery_input(query: str) -> str:
    """Query text reduced to OR-able terms for ``websearch_to_tsquery``.

    Punctuation is stripped rather than escaped: a stray quote makes Postgres
    reject the whole query, and losing it costs nothing a user meant.
    """
    words = re.findall(r"[\w']+", query.lower())
    return " or ".join(w for w in words if len(w) > 1)


async def _vector_candidates(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query_vector: list[float],
    limit: int,
    file_id: uuid.UUID | None,
) -> list[tuple[FileChunk, str, float]]:
    """Nearest chunks by cosine distance, as ``(chunk, filename, similarity)``."""
    distance = FileChunk.embedding.cosine_distance(query_vector).label("distance")
    stmt = (
        select(FileChunk, File.original_filename, distance)
        .join(File, File.id == FileChunk.file_id)
        # Tenant filter in the statement itself. Ownership is also enforced by
        # RLS, but a retrieval path is the last place to rely on one layer.
        .where(FileChunk.user_id == user_id, FileChunk.embedding.isnot(None))
        .order_by(distance)
        .limit(limit)
    )
    if file_id is not None:
        stmt = stmt.where(FileChunk.file_id == file_id)
    rows = (await session.execute(stmt)).all()
    # pgvector cosine distance is 1 - cosine similarity.
    return [(chunk, name, 1.0 - float(dist)) for chunk, name, dist in rows]


async def _text_candidates(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    limit: int,
    file_id: uuid.UUID | None,
) -> list[tuple[FileChunk, str]]:
    """Chunks matching the query lexically, best ``ts_rank`` first."""
    terms = _to_tsquery_input(query)
    if not terms:
        return []
    vector = func.to_tsvector(literal("english"), FileChunk.content)
    tsquery = func.websearch_to_tsquery(literal("english"), literal(terms))
    rank = func.ts_rank(vector, tsquery).cast(Float).label("rank")
    stmt = (
        select(FileChunk, File.original_filename)
        .join(File, File.id == FileChunk.file_id)
        .where(FileChunk.user_id == user_id, vector.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(limit)
    )
    if file_id is not None:
        stmt = stmt.where(FileChunk.file_id == file_id)
    return [(chunk, name) for chunk, name in (await session.execute(stmt)).all()]


async def search(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    query_vector: list[float] | None,
    limit: int,
    file_id: uuid.UUID | None = None,
    min_similarity: float = FILE_RETRIEVAL_MIN_SIMILARITY,
) -> list[RetrievedChunk]:
    """Run both retrievers, fuse, gate, and return the survivors.

    ``query_vector`` may be ``None`` when embeddings are unavailable; the
    lexical half still runs, so search degrades rather than disappearing.
    """
    cleaned = normalize_query(query)
    if not cleaned:
        return []

    candidates = max(limit, FILE_RETRIEVAL_CANDIDATES)
    with langfuse_obs.observe_retrieval(
        "file.hybrid_search",
        input=cleaned,
        metadata={"limit": limit, "file_id": str(file_id) if file_id else None},
    ) as span:
        vector_hits = (
            await _vector_candidates(
                session,
                user_id=user_id,
                query_vector=query_vector,
                limit=candidates,
                file_id=file_id,
            )
            if query_vector
            else []
        )
        text_hits = await _text_candidates(
            session,
            user_id=user_id,
            query=cleaned,
            limit=candidates,
            file_id=file_id,
        )

        fused = _fuse(vector_hits, text_hits)
        gated = [r for r in fused if _passes_gate(r, min_similarity)]
        span.update(
            metadata={
                "vector_hits": len(vector_hits),
                "text_hits": len(text_hits),
                "fused": len(fused),
                "kept": len(gated[:limit]),
            }
        )
    return gated[:limit]


def _fuse(
    vector_hits: list[tuple[FileChunk, str, float]],
    text_hits: list[tuple[FileChunk, str]],
) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion over the two ranked lists.

    ``1 / (k + rank)`` per list, summed. ``k`` damps the difference between the
    top few positions so a chunk found by *both* retrievers outranks one that
    merely came first in a single list — which is the whole point of running
    two.
    """
    k = FILE_RETRIEVAL_RRF_K
    scores: dict[uuid.UUID, float] = {}
    similarity: dict[uuid.UUID, float] = {}
    seen: dict[uuid.UUID, tuple[FileChunk, str]] = {}
    from_vector: set[uuid.UUID] = set()
    from_text: set[uuid.UUID] = set()

    for rank, (chunk, name, sim) in enumerate(vector_hits, start=1):
        scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
        similarity[chunk.id] = sim
        seen[chunk.id] = (chunk, name)
        from_vector.add(chunk.id)

    for rank, (chunk, name) in enumerate(text_hits, start=1):
        scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank)
        seen.setdefault(chunk.id, (chunk, name))
        from_text.add(chunk.id)

    results = [
        RetrievedChunk(
            chunk=seen[cid][0],
            filename=seen[cid][1],
            similarity=similarity.get(cid, 0.0),
            score=score,
            matched_vector=cid in from_vector,
            matched_text=cid in from_text,
        )
        for cid, score in scores.items()
    ]
    # Deterministic: score, then chunk position, so equal scores never reorder
    # between runs.
    results.sort(key=lambda r: (-r.score, r.chunk.file_id.hex, r.chunk.chunk_index))
    return results


def _passes_gate(result: RetrievedChunk, min_similarity: float) -> bool:
    """Whether a candidate is relevant enough to put in front of the model.

    A lexical-only hit is kept: it contains the literal words asked about, which
    is evidence in its own right and the case vector search is worst at. A
    semantic-only hit must clear the floor, because "nearest of everything I
    own" is not the same as "related to the question".
    """
    if result.matched_text:
        return True
    return result.similarity >= min_similarity
