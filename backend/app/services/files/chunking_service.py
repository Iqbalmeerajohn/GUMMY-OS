"""Deterministic text chunking for the Files System (M6).

Splits extracted text into overlapping, fixed-size character windows. The
algorithm is intentionally **deterministic and dependency-free**: the same
input text always yields the same chunks, so chunks are a stable substrate the
future RAG layer can embed and re-embed without drift. Token counts are an
approximation (chars ÷ divisor) — we deliberately do not call a tokenizer here,
keeping chunking pure and fast.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.constants import (
    FILE_CHUNK_OVERLAP_CHARS,
    FILE_CHUNK_SIZE_CHARS,
    FILE_CHUNK_TOKEN_DIVISOR,
)
from app.services.files.extraction_service import DocumentSegment


@dataclass(frozen=True)
class TextChunk:
    """One deterministic slice of a document's text."""

    index: int
    content: str
    token_count: int
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class SegmentChunk:
    """A chunk plus the provenance of the segment it was cut from.

    Whatever is not None here is what the answer can honestly cite.
    """

    index: int
    content: str
    token_count: int
    page: int | None = None
    section: str | None = None
    row_start: int | None = None
    row_end: int | None = None

    def as_metadata(self) -> dict:
        """The subset worth persisting on the chunk row (omitting empties)."""
        fields = {
            "page": self.page,
            "section": self.section,
            "row_start": self.row_start,
            "row_end": self.row_end,
        }
        return {k: v for k, v in fields.items() if v is not None}


def chunk_text(
    text: str,
    *,
    chunk_size: int = FILE_CHUNK_SIZE_CHARS,
    overlap: int = FILE_CHUNK_OVERLAP_CHARS,
) -> list[TextChunk]:
    """Chunk ``text`` into overlapping windows (deterministic, gap-free indices).

    Whitespace-only input (or empty) yields no chunks. Windows advance by
    ``chunk_size - overlap`` so consecutive chunks share ``overlap`` characters
    of context. Each chunk's text is stripped; blank windows are skipped but do
    not break index continuity (indices are assigned to emitted chunks in order).
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must satisfy 0 <= overlap < chunk_size")

    normalized = text.strip()
    if not normalized:
        return []

    step = chunk_size - overlap
    chunks: list[TextChunk] = []
    index = 0
    start = 0
    length = len(normalized)
    while start < length:
        end = min(start + chunk_size, length)
        window = normalized[start:end].strip()
        if window:
            chunks.append(
                TextChunk(
                    index=index,
                    content=window,
                    token_count=_approx_tokens(window),
                    start_offset=start,
                    end_offset=end,
                )
            )
            index += 1
        if end >= length:
            break
        start += step
    return chunks


def _approx_tokens(text: str) -> int:
    """Approximate token count for a chunk (chars ÷ divisor, min 1)."""
    return max(1, len(text) // FILE_CHUNK_TOKEN_DIVISOR)


def chunk_segments(
    segments: list[DocumentSegment],
    *,
    chunk_size: int = FILE_CHUNK_SIZE_CHARS,
    overlap: int = FILE_CHUNK_OVERLAP_CHARS,
) -> list[SegmentChunk]:
    """Chunk within segment boundaries, carrying each segment's provenance.

    Chunking the whole document as one string is what loses attribution: a
    window can straddle two PDF pages, and the resulting chunk honestly belongs
    to neither. Cutting inside a segment means every chunk has exactly one page,
    one heading, or one row range.

    Two consequences worth stating. A segment shorter than ``chunk_size`` yields
    one chunk regardless of how short it is — a two-line Markdown section is a
    real section, not something to glue onto its neighbour. And a CSV segment's
    header is prefixed onto every chunk cut from it, because a grid of values
    with no column names is not retrievable and not readable.

    Indices are continuous across the whole document, so ``chunk_index`` stays
    gap-free and ordering still reconstructs the original.
    """
    chunks: list[SegmentChunk] = []
    index = 0
    for segment in segments:
        body = segment.content.strip()
        if not body:
            continue
        prefix = f"{segment.header}\n" if segment.header else ""
        # The header costs room in every window; take it out of the budget so a
        # wide spreadsheet cannot push the actual rows down to nothing.
        budget = max(1, chunk_size - len(prefix))
        for piece in chunk_text(
            body, chunk_size=budget, overlap=min(overlap, budget - 1)
        ):
            chunks.append(
                SegmentChunk(
                    index=index,
                    content=f"{prefix}{piece.content}",
                    token_count=_approx_tokens(f"{prefix}{piece.content}"),
                    page=segment.page,
                    section=segment.section,
                    row_start=segment.row_start,
                    row_end=segment.row_end,
                )
            )
            index += 1
    return chunks
