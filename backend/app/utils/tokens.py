"""Lightweight token estimation.

A character-count heuristic — good enough for budgeting the memory context without
paying for a real tokenizer call. Replace with a model tokenizer if precise
accounting is ever needed.
"""

from __future__ import annotations

from app.core.constants import APPROX_CHARS_PER_TOKEN


def estimate_tokens(text: str) -> int:
    """Roughly estimate the token count of a string (never returns 0)."""
    if not text:
        return 0
    return max(1, len(text) // APPROX_CHARS_PER_TOKEN)
