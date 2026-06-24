"""KnowledgeRanker tests (M7) — cross-source fusion, pure (no DB).

Proves the ranker projects each source onto one comparable axis and enforces the
priority order: attached files > relevant files > goals > memories.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.knowledge import knowledge_ranker
from app.services.knowledge.knowledge_retrieval_service import (
    SOURCE_FILE,
    SOURCE_GOAL,
    SOURCE_MEMORY,
    SOURCE_SEARCH,
    KnowledgeItem,
    UnifiedKnowledgeContext,
)

_NOW = datetime(2026, 6, 24, tzinfo=UTC)


def _memory(content: str, score: float) -> KnowledgeItem:
    return KnowledgeItem(
        source=SOURCE_MEMORY,
        item_id=content,
        content=content,
        label="career",
        source_score=score,
        metadata={"category": "career"},
    )


def _goal(title: str, priority: str, target: datetime | None = None) -> KnowledgeItem:
    return KnowledgeItem(
        source=SOURCE_GOAL,
        item_id=title,
        content=title,
        label=title,
        source_score=0.0,
        metadata={"title": title, "priority": priority, "_target_dt": target},
    )


def _file(name: str, order: int, *, attached: bool = False) -> KnowledgeItem:
    return KnowledgeItem(
        source=SOURCE_FILE,
        item_id=name,
        content=f"content of {name}",
        label=name,
        source_score=0.0,
        metadata={"filename": name, "order": order, "attached": attached},
    )


def _search(title: str, order: int) -> KnowledgeItem:
    return KnowledgeItem(
        source=SOURCE_SEARCH,
        item_id=f"https://ex.com/{order}",
        content=title,
        label=title,
        source_score=0.0,
        metadata={"title": title, "url": f"https://ex.com/{order}", "order": order},
    )


def _ctx(*items: KnowledgeItem) -> UnifiedKnowledgeContext:
    return UnifiedKnowledgeContext(
        query="q",
        memories=[i for i in items if i.source == SOURCE_MEMORY],
        goals=[i for i in items if i.source == SOURCE_GOAL],
        files=[i for i in items if i.source == SOURCE_FILE],
        search=[i for i in items if i.source == SOURCE_SEARCH],
    )


# ── Goal scoring ──────────────────────────────────────────────────────────────


def test_priority_score_orders_high_above_low() -> None:
    assert knowledge_ranker.priority_score("high") > knowledge_ranker.priority_score(
        "low"
    )


def test_deadline_proximity_is_urgent_when_near_and_zero_when_far() -> None:
    soon = _NOW + timedelta(days=1)
    far = _NOW + timedelta(days=365)
    assert knowledge_ranker.deadline_proximity(soon, now=_NOW) > 0.9
    assert knowledge_ranker.deadline_proximity(far, now=_NOW) == 0.0
    assert knowledge_ranker.deadline_proximity(None, now=_NOW) == 0.0


def test_overdue_goal_scores_full_urgency() -> None:
    overdue = _NOW - timedelta(days=5)
    assert knowledge_ranker.deadline_proximity(overdue, now=_NOW) == 1.0


def test_high_priority_goal_outranks_low_priority_goal() -> None:
    ranked = knowledge_ranker.rank(
        _ctx(_goal("ship", "high"), _goal("tidy", "low")), now=_NOW
    )
    assert ranked[0].content == "ship"


# ── Attachment priority (the headline guarantee) ──────────────────────────────


def test_attached_file_outranks_everything() -> None:
    ranked = knowledge_ranker.rank(
        _ctx(
            _memory("strong memory", 0.99),
            _goal("urgent goal", "high", _NOW + timedelta(days=1)),
            _file("resume.pdf", 0, attached=True),
        ),
        now=_NOW,
    )
    assert ranked[0].source == SOURCE_FILE
    assert ranked[0].metadata["attached"] is True


def test_attached_file_outranks_unattached_file() -> None:
    ranked = knowledge_ranker.rank(
        _ctx(_file("other.pdf", 0), _file("resume.pdf", 0, attached=True)),
        now=_NOW,
    )
    assert ranked[0].label == "resume.pdf"


def test_earlier_keyword_match_outranks_later_one() -> None:
    ranked = knowledge_ranker.rank(_ctx(_file("b.txt", 3), _file("a.txt", 0)), now=_NOW)
    assert ranked[0].label == "a.txt"


# ── Cross-source priority order: files > goals > memories at parity ───────────


def test_every_item_gets_a_rank_score() -> None:
    ranked = knowledge_ranker.rank(
        _ctx(_memory("m", 0.5), _goal("g", "medium"), _file("f.txt", 0)),
        now=_NOW,
    )
    assert all(item.rank_score > 0 for item in ranked)
    # Sorted descending.
    scores = [item.rank_score for item in ranked]
    assert scores == sorted(scores, reverse=True)


def test_empty_context_ranks_to_empty_list() -> None:
    assert knowledge_ranker.rank(_ctx(), now=_NOW) == []


# ── Web search fusion (M8.5): supplemental, ranked below user knowledge ───────


def test_search_ranks_below_memory() -> None:
    # A weak memory still outranks a top web-search hit (search is supplemental).
    ranked = knowledge_ranker.rank(
        _ctx(_memory("weak memory", 0.3), _search("Top hit", 0)), now=_NOW
    )
    assert ranked[0].source == SOURCE_MEMORY
    assert ranked[-1].source == SOURCE_SEARCH


def test_search_is_included_in_ranking() -> None:
    ranked = knowledge_ranker.rank(_ctx(_search("a", 0), _search("b", 1)), now=_NOW)
    assert [i.label for i in ranked] == ["a", "b"]
    assert all(i.rank_score > 0 for i in ranked)
