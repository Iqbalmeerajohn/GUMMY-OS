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


@dataclass(frozen=True)
class TextChunk:
    """One deterministic slice of a document's text."""

    index: int
    content: str
    token_count: int
    start_offset: int
    end_offset: int


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
