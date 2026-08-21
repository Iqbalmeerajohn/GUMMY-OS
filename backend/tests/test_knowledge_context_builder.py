"""KnowledgeContextBuilder tests (M7) — compression + rendering, pure (no DB).

Proves the builder dedupes within a source, respects the token budget, preserves
source attribution, and renders the three sections (+ file inventory).
"""

from __future__ import annotations

from app.services.knowledge import knowledge_context_builder
from app.services.knowledge.knowledge_retrieval_service import (
    SOURCE_FILE,
    SOURCE_GOAL,
    SOURCE_MEMORY,
    SOURCE_SEARCH,
    KnowledgeItem,
)


def _search(title: str, url: str, snippet: str = "snip") -> KnowledgeItem:
    return KnowledgeItem(
        source=SOURCE_SEARCH,
        item_id=url,
        content=f"{title} — {snippet}",
        label=title,
        source_score=0.6,
        rank_score=0.3,
        metadata={
            "title": title,
            "url": url,
            "snippet": snippet,
            "provider": "tavily",
            "order": 0,
        },
    )


def _memory(content: str, score: float = 0.5) -> KnowledgeItem:
    return KnowledgeItem(
        source=SOURCE_MEMORY,
        item_id=content,
        content=content,
        label="career",
        source_score=score,
        rank_score=score,
        metadata={"category": "career"},
    )


def _goal(title: str) -> KnowledgeItem:
    return KnowledgeItem(
        source=SOURCE_GOAL,
        item_id=title,
        content=title,
        label=title,
        source_score=0.8,
        rank_score=0.8,
        metadata={
            "title": title,
            "priority": "high",
            "target_date": "2026-07-02",
            "progress_percentage": 20,
        },
    )


def _file(name: str, content: str, chunk: int = 0) -> KnowledgeItem:
    return KnowledgeItem(
        source=SOURCE_FILE,
        item_id=name,
        content=content,
        label=name,
        source_score=0.6,
        rank_score=1.6,
        metadata={"filename": name, "chunk_index": chunk, "order": chunk},
    )


def test_renders_three_attributed_sections() -> None:
    compiled = knowledge_context_builder.build(
        [_file("r.pdf", "revenue up"), _goal("Get job"), _memory("likes python")]
    )
    block = compiled.block
    assert "Memories:" in block
    assert "Goals:" in block
    assert "Files:" in block
    # Source attribution preserved on every line.
    assert "[memory" in block
    assert "[goal]" in block
    assert "[file]" in block


def test_search_section_rendered_only_when_present() -> None:
    # No search items → no Search section.
    plain = knowledge_context_builder.build([_memory("likes python")])
    assert "Search" not in plain.block

    compiled = knowledge_context_builder.build(
        [_memory("likes python"), _search("AI News", "https://ex.com/ai")]
    )
    assert "Search" in compiled.block
    assert "https://ex.com/ai" in compiled.block
    # Labelled [web], not [search:<provider>]: the vendor name is machinery,
    # and having it in the model's context is how it reached an answer.
    assert "[web]" in compiled.block
    assert "tavily" not in compiled.block.lower()
    assert compiled.search_used == 1


def test_duplicate_memories_are_compressed() -> None:
    compiled = knowledge_context_builder.build(
        [_memory("same fact", 0.9), _memory("same fact", 0.4)]
    )
    assert compiled.memories_used == 1


def test_duplicate_goals_compressed_by_title() -> None:
    compiled = knowledge_context_builder.build(
        [_goal("Get AI job"), _goal("Get AI job")]
    )
    assert compiled.goals_used == 1


def test_overlapping_file_chunks_compressed_by_content() -> None:
    compiled = knowledge_context_builder.build(
        [_file("a.txt", "identical chunk", 0), _file("a.txt", "identical chunk", 1)]
    )
    assert compiled.files_used == 1


def test_token_budget_caps_selection_but_keeps_at_least_one() -> None:
    big = [_memory(f"fact number {i} " * 50, score=1.0 - i * 0.01) for i in range(20)]
    compiled = knowledge_context_builder.build(big, token_budget=60)
    assert 1 <= compiled.memories_used < 20
    assert compiled.token_estimate > 0


def test_inventory_renders_even_without_file_content() -> None:
    inventory = [
        {
            "filename": "notes.txt",
            "processing_status": "completed",
            "chunk_count": 3,
            "uploaded_at": "2026-06-24",
        }
    ]
    compiled = knowledge_context_builder.build([], inventory=inventory)
    assert "Uploaded files:" in compiled.block
    assert "notes.txt" in compiled.block


def test_empty_input_yields_empty_block() -> None:
    compiled = knowledge_context_builder.build([])
    assert compiled.is_empty
    assert compiled.block == ""
