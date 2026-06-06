"""Pure ranking-math tests (no database)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.constants import (
    RETRIEVAL_WEIGHT_CONFIDENCE,
    RETRIEVAL_WEIGHT_IMPORTANCE,
    RETRIEVAL_WEIGHT_RECENCY,
    RETRIEVAL_WEIGHT_SEMANTIC,
)
from app.services.memory.memory_retrieval_service import (
    compute_hybrid_score,
    compute_recency_score,
    reinforced_scores,
)


def test_weights_sum_to_one() -> None:
    total = (
        RETRIEVAL_WEIGHT_SEMANTIC
        + RETRIEVAL_WEIGHT_IMPORTANCE
        + RETRIEVAL_WEIGHT_CONFIDENCE
        + RETRIEVAL_WEIGHT_RECENCY
    )
    assert abs(total - 1.0) < 1e-9


def test_recency_score_decays() -> None:
    now = datetime(2026, 6, 7, tzinfo=UTC)
    assert compute_recency_score(now, now=now) == 1.0
    half = compute_recency_score(now - timedelta(days=30), now=now)
    assert abs(half - 0.5) < 1e-6
    quarter = compute_recency_score(now - timedelta(days=60), now=now)
    assert abs(quarter - 0.25) < 1e-6


def test_recency_handles_naive_datetime() -> None:
    now = datetime(2026, 6, 7, tzinfo=UTC)
    naive = datetime(2026, 6, 7)  # intentionally tz-naive
    assert compute_recency_score(naive, now=now) == 1.0


def test_hybrid_score_is_weighted_blend() -> None:
    score = compute_hybrid_score(
        semantic_similarity=1.0,
        importance_score=1.0,
        confidence_score=1.0,
        recency_score=1.0,
    )
    assert abs(score - 1.0) < 1e-9

    only_semantic = compute_hybrid_score(
        semantic_similarity=1.0,
        importance_score=0.0,
        confidence_score=0.0,
        recency_score=0.0,
    )
    assert abs(only_semantic - RETRIEVAL_WEIGHT_SEMANTIC) < 1e-9


def test_hybrid_score_clamps_inputs() -> None:
    score = compute_hybrid_score(
        semantic_similarity=-0.5,  # negative cosine -> clamped to 0
        importance_score=2.0,  # clamped to 1
        confidence_score=0.0,
        recency_score=0.0,
    )
    assert abs(score - RETRIEVAL_WEIGHT_IMPORTANCE) < 1e-9


def test_hybrid_score_monotonic_in_similarity() -> None:
    low = compute_hybrid_score(
        semantic_similarity=0.2,
        importance_score=0.5,
        confidence_score=0.5,
        recency_score=0.5,
    )
    high = compute_hybrid_score(
        semantic_similarity=0.9,
        importance_score=0.5,
        confidence_score=0.5,
        recency_score=0.5,
    )
    assert high > low


def test_reinforced_scores_diminish_and_cap() -> None:
    new_imp, new_conf = reinforced_scores(0.5, 0.5)
    assert new_imp == 0.5 + 0.05 * 0.5
    assert new_conf == 0.5 + 0.03 * 0.5

    capped_imp, capped_conf = reinforced_scores(1.0, 1.0)
    assert capped_imp == 1.0
    assert capped_conf == 1.0
