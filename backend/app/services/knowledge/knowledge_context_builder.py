"""KnowledgeContextBuilder — compress ranked knowledge into a prompt block.

The prompt budget is finite, so the builder takes the ranker's cross-source list
and:

* **compresses** — drops duplicate memories (same content), duplicate goals
  (same title), and overlapping file chunks (same file + chunk, or identical
  content);
* **budgets** — selects items in rank order until a shared token budget is hit
  (always keeping at least one when any exist);
* **renders** — groups the survivors back by source into a single attributed
  ``<knowledge>`` body with ``Memories:`` / ``Goals:`` / ``Files:`` sections,
  every line tagged with its origin so provenance survives into the prompt.

Pure and I/O-free apart from an optional Langfuse span — fully unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.constants import (
    KNOWLEDGE_CONTEXT_TOKEN_BUDGET,
    KNOWLEDGE_SEARCH_SNIPPET_CHAR_CAP,
)
from app.observability import langfuse as langfuse_obs
from app.services.knowledge.knowledge_retrieval_service import (
    SOURCE_FILE,
    SOURCE_GOAL,
    SOURCE_MEMORY,
    SOURCE_SEARCH,
    KnowledgeItem,
)
from app.utils.tokens import estimate_tokens


@dataclass(frozen=True)
class CompiledKnowledge:
    """The compressed, token-budgeted knowledge ready for the prompt."""

    # Selected items, in rank order (mixed sources).
    items: list[KnowledgeItem] = field(default_factory=list)
    # The rendered ``<knowledge>`` body (sections), or "" when nothing selected.
    block: str = ""
    token_estimate: int = 0
    memories_used: int = 0
    goals_used: int = 0
    files_used: int = 0
    search_used: int = 0
    # Stable per-item keys that survived selection (for the diagnostics verdict).
    included_keys: frozenset[str] = frozenset()

    @property
    def is_empty(self) -> bool:
        return not self.block


def item_key(item: KnowledgeItem) -> str:
    """A stable identity for dedupe + diagnostics (file chunks differ by index)."""
    chunk = item.metadata.get("chunk_index", "")
    return f"{item.source}:{item.item_id}:{chunk}"


def _dedupe_signature(item: KnowledgeItem) -> str:
    """Content signature used to drop semantic duplicates within a source."""
    if item.source == SOURCE_GOAL:
        title = item.metadata.get("title", item.content)
        return f"{SOURCE_GOAL}:{title.strip().lower()}"
    return f"{item.source}:{item.content.strip().lower()}"


def _render_memory(item: KnowledgeItem) -> str:
    category = item.metadata.get("category", "")
    tag = f"[memory:{category}]" if category else "[memory]"
    return f"- {tag} {item.content}"


def _render_goal(item: KnowledgeItem) -> str:
    parts = [f"priority: {item.metadata.get('priority', 'medium')}"]
    target = item.metadata.get("target_date")
    if target:
        parts.append(f"target: {target}")
    parts.append(f"progress: {item.metadata.get('progress_percentage', 0)}%")
    return f"- [goal] {item.metadata.get('title', item.content)} ({', '.join(parts)})"


def _render_file(item: KnowledgeItem) -> str:
    return f"- [file] [{item.metadata.get('filename', 'file')}] {item.content}"


def _render_search(item: KnowledgeItem) -> str:
    """Render a web-search hit with source/title/url/snippet (B8)."""
    title = item.metadata.get("title", item.content)
    url = item.metadata.get("url", "")
    snippet = str(item.metadata.get("snippet", ""))[:KNOWLEDGE_SEARCH_SNIPPET_CHAR_CAP]
    provider = item.metadata.get("provider", "web")
    line = f"- [search:{provider}] {title} ({url})"
    return f"{line}\n  {snippet}" if snippet else line


def _render_inventory(inventory: list[dict]) -> str:
    lines: list[str] = []
    for f in inventory:
        if not isinstance(f, dict):
            continue
        lines.append(
            f"- {f.get('filename', '')} "
            f"({f.get('processing_status', 'unknown')}, "
            f"{f.get('chunk_count', 0)} chunks, "
            f"uploaded {f.get('uploaded_at', 'n/a')})"
        )
    return "Uploaded files:\n" + "\n".join(lines) if lines else ""


def build(
    ranked: list[KnowledgeItem],
    *,
    inventory: list[dict] | None = None,
    token_budget: int = KNOWLEDGE_CONTEXT_TOKEN_BUDGET,
) -> CompiledKnowledge:
    """Compress + budget the ranked items and render the ``<knowledge>`` body.

    ``inventory`` (file metadata) is rendered as a small always-present preamble
    to the Files section so "what files do I have?" stays answerable even when no
    file *content* was selected; its tokens count against the budget first.
    """
    inventory = inventory or []
    with langfuse_obs.observe_operation(
        "knowledge.compress",
        metadata={"candidates": len(ranked), "token_budget": token_budget},
    ) as span:
        inventory_block = _render_inventory(inventory)
        used_tokens = estimate_tokens(inventory_block) if inventory_block else 0

        selected: list[KnowledgeItem] = []
        seen_signatures: set[str] = set()
        for item in ranked:
            sig = _dedupe_signature(item)
            if sig in seen_signatures:
                continue  # compression: drop duplicate/overlapping content
            renderer = _RENDERERS[item.source]
            cost = estimate_tokens(renderer(item))
            if selected and used_tokens + cost > token_budget:
                continue  # over budget — skip (but always keep the first item)
            seen_signatures.add(sig)
            selected.append(item)
            used_tokens += cost

        block = _render_block(selected, inventory_block)
        memories = sum(1 for i in selected if i.source == SOURCE_MEMORY)
        goals = sum(1 for i in selected if i.source == SOURCE_GOAL)
        files = sum(1 for i in selected if i.source == SOURCE_FILE)
        searches = sum(1 for i in selected if i.source == SOURCE_SEARCH)
        span.update(
            metadata={
                "selected": len(selected),
                "memories": memories,
                "goals": goals,
                "files": files,
                "search": searches,
                "token_estimate": used_tokens,
            }
        )
        return CompiledKnowledge(
            items=selected,
            block=block,
            token_estimate=used_tokens,
            memories_used=memories,
            goals_used=goals,
            files_used=files,
            search_used=searches,
            included_keys=frozenset(item_key(i) for i in selected),
        )


_RENDERERS = {
    SOURCE_MEMORY: _render_memory,
    SOURCE_GOAL: _render_goal,
    SOURCE_FILE: _render_file,
    SOURCE_SEARCH: _render_search,
}


def _render_block(selected: list[KnowledgeItem], inventory_block: str) -> str:
    """Group selected items by source into the attributed ``<knowledge>`` body."""
    memories = [i for i in selected if i.source == SOURCE_MEMORY]
    goals = [i for i in selected if i.source == SOURCE_GOAL]
    files = [i for i in selected if i.source == SOURCE_FILE]
    searches = [i for i in selected if i.source == SOURCE_SEARCH]

    sections: list[str] = []
    if memories:
        sections.append("Memories:\n" + "\n".join(_render_memory(i) for i in memories))
    if goals:
        sections.append("Goals:\n" + "\n".join(_render_goal(i) for i in goals))

    file_parts: list[str] = []
    if inventory_block:
        file_parts.append(inventory_block)
    if files:
        file_parts.append(
            "Relevant content from the files:\n"
            + "\n".join(_render_file(i) for i in files)
        )
    if file_parts:
        sections.append("Files:\n" + "\n\n".join(file_parts))

    # Supplemental live web results, last (B8) — only when search hits survived.
    if searches:
        sections.append(
            "Search (live web results — supplemental, verify before relying on):\n"
            + "\n".join(_render_search(i) for i in searches)
        )

    return "\n\n".join(sections)
