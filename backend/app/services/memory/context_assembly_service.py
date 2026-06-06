"""Context assembly — turn ranked memories into a token-budgeted context pack.

Receives candidate memories (already ranked by the retrieval engine), removes
duplicates, keeps the highest-scoring ones, and selects as many as fit a token
budget. Produces a provider-agnostic ``ContextPackage`` for the prompt builder.

Pure and I/O-free — fully unit-testable without a database or model.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.constants import (
    DEFAULT_CONTEXT_MAX_MEMORIES,
    DEFAULT_CONTEXT_TOKEN_BUDGET,
)
from app.utils.tokens import estimate_tokens


@dataclass(frozen=True)
class ContextMemory:
    """A single memory considered for (or selected into) the context pack."""

    content: str
    category: str
    score: float


@dataclass(frozen=True)
class ContextPackage:
    """The assembled, token-budgeted set of memories for a prompt."""

    memories: list[ContextMemory]
    token_estimate: int


def render_memory_line(memory: ContextMemory) -> str:
    """Single-line rendering used for both token estimation and prompting."""
    return f"[{memory.category}] {memory.content}"


def assemble_context(
    candidates: list[ContextMemory],
    *,
    token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET,
    max_memories: int = DEFAULT_CONTEXT_MAX_MEMORIES,
) -> ContextPackage:
    """Dedupe, rank, and select candidates within a token budget."""
    # Dedupe by normalized content, keeping the highest-scoring occurrence.
    best_by_content: dict[str, ContextMemory] = {}
    for candidate in candidates:
        key = candidate.content.strip().lower()
        if not key:
            continue
        existing = best_by_content.get(key)
        if existing is None or candidate.score > existing.score:
            best_by_content[key] = candidate

    ranked = sorted(best_by_content.values(), key=lambda m: m.score, reverse=True)

    selected: list[ContextMemory] = []
    used_tokens = 0
    for memory in ranked:
        if len(selected) >= max_memories:
            break
        cost = estimate_tokens(render_memory_line(memory))
        if selected and used_tokens + cost > token_budget:
            # Always allow at least one memory; otherwise respect the budget.
            continue
        selected.append(memory)
        used_tokens += cost

    return ContextPackage(memories=selected, token_estimate=used_tokens)
