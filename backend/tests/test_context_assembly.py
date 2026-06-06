"""Context assembly tests: dedupe, ranking, token budget (pure, no DB)."""

from __future__ import annotations

from app.services.memory.context_assembly_service import (
    ContextMemory,
    assemble_context,
)


def _mem(content: str, score: float, category: str = "career") -> ContextMemory:
    return ContextMemory(content=content, category=category, score=score)


def test_orders_by_score_descending() -> None:
    package = assemble_context(
        [_mem("a", 0.2), _mem("b", 0.9), _mem("c", 0.5)],
    )
    assert [m.content for m in package.memories] == ["b", "c", "a"]


def test_dedupes_keeping_highest_score() -> None:
    package = assemble_context(
        [_mem("Targeting Qualcomm", 0.4), _mem("targeting qualcomm  ", 0.8)],
    )
    assert len(package.memories) == 1
    assert package.memories[0].score == 0.8


def test_respects_token_budget() -> None:
    big = "x" * 400  # ~100 tokens via the chars/4 heuristic
    package = assemble_context(
        [_mem(big, 0.9), _mem(big, 0.8), _mem(big, 0.7)],
        token_budget=150,
    )
    # First fits; the budget then blocks the rest.
    assert len(package.memories) == 1
    assert package.token_estimate <= 150 or len(package.memories) == 1


def test_always_includes_at_least_one() -> None:
    huge = "y" * 10_000
    package = assemble_context([_mem(huge, 0.9)], token_budget=10)
    assert len(package.memories) == 1


def test_respects_max_memories() -> None:
    package = assemble_context(
        [_mem(f"m{i}", 1.0 - i * 0.01) for i in range(10)],
        token_budget=100_000,
        max_memories=3,
    )
    assert len(package.memories) == 3


def test_empty_candidates_yield_empty_pack() -> None:
    package = assemble_context([])
    assert package.memories == []
    assert package.token_estimate == 0
