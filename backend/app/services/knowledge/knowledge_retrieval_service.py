"""KnowledgeRetrievalService — fan out to every knowledge source as one unit.

Turns a query (+ optional attachments) into a :class:`UnifiedKnowledgeContext`
that carries ranked candidates from all three sources — **memories, goals,
files** — each item tagged with its provenance (``source``). This is the single
retrieval seam chat and (from M8) agents build on, replacing the independent
per-source lookups the turn used to wire by hand.

Graceful degradation is the contract: **no single source may ever take down a
turn.** Each source is isolated so a failure in one degrades to the others:

* **memory** — try/except (the hybrid retriever owns its own commit for
  reinforcement, so it cannot be wrapped in a SAVEPOINT);
* **goals** — a SAVEPOINT (``begin_nested``) + degrade-to-empty, mirroring the
  goal-lookup resilience pattern: on PostgreSQL a failed statement aborts the
  whole transaction, so a bare try/except still poisons the turn — the savepoint
  confines the rollback to this lookup;
* **files** — delegated to ``file_context_service`` (its search path is already
  internally best-effort; the *attachment* path lets a 404 propagate because the
  user explicitly referenced that file — a silent miss would be wrong).

The service retrieves and attributes; it does **not** rank or compress (that is
``knowledge_ranker`` / ``knowledge_context_builder``). Read-only apart from
memory reinforcement; owns no unit of work of its own.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    CONTEXT_MAX_GOALS,
    KNOWLEDGE_FILE_CHUNK_CHAR_CAP,
    KNOWLEDGE_MAX_FILES,
    KNOWLEDGE_MAX_MEMORIES,
)
from app.core.observability import capture_exception
from app.observability import analytics
from app.observability import langfuse as langfuse_obs
from app.repositories import goal_repository
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.files import file_context_service
from app.services.memory import memory_retrieval_service

logger = logging.getLogger(__name__)

# Provenance tags (every item keeps its origin).
SOURCE_MEMORY = "memory"
SOURCE_GOAL = "goal"
SOURCE_FILE = "file"
# Live web search (M8.5): a *supplemental* source fused after the user's own
# knowledge. Never overrides memories/goals/files (the ranker weights it lower).
SOURCE_SEARCH = "search"


@dataclass(frozen=True)
class KnowledgeItem:
    """One unit of knowledge with its provenance and scores.

    ``source_score`` is the item's native score on its own source's scale (the
    memory hybrid score, the goal's priority/deadline score, the file's
    retrieval score). ``rank_score`` is the cross-source comparable score the
    ranker assigns — ``0.0`` until :mod:`knowledge_ranker` fills it in.
    """

    source: str
    item_id: str
    content: str
    # A short display label: memory category, goal title, or filename.
    label: str
    source_score: float
    metadata: dict
    rank_score: float = 0.0


@dataclass(frozen=True)
class UnifiedKnowledgeContext:
    """The fused retrieval result across memories, goals, and files."""

    query: str
    memories: list[KnowledgeItem] = field(default_factory=list)
    goals: list[KnowledgeItem] = field(default_factory=list)
    files: list[KnowledgeItem] = field(default_factory=list)
    # Live web-search hits (M8.5) — supplemental, ranked below the user's own
    # knowledge. Empty unless the agent is search-eligible and the query matched.
    search: list[KnowledgeItem] = field(default_factory=list)
    # Lightweight file metadata (so the assistant can answer "what files do I
    # have?" from the same context). Mirrors ``FileContext.inventory``.
    inventory: list[dict] = field(default_factory=list)
    # The sources that actually contributed candidates (provenance for the turn).
    sources_used: list[str] = field(default_factory=list)
    attachment_file_ids: list[uuid.UUID] = field(default_factory=list)

    @property
    def all_items(self) -> list[KnowledgeItem]:
        return [*self.memories, *self.goals, *self.files, *self.search]

    @property
    def is_empty(self) -> bool:
        return (
            not self.memories
            and not self.goals
            and not self.files
            and not self.search
            and (not self.inventory)
        )


def search_items_from_results(results: list) -> list[KnowledgeItem]:
    """Adapt provider ``SearchResult``s into ``SOURCE_SEARCH`` knowledge items.

    Pure (no I/O): used by both reply paths to fuse live search into the same
    ranker + builder as the user's own knowledge. ``order`` drives the ranker's
    decay (best hit first); ``url``/``domain`` survive for citation/rendering.
    """
    items: list[KnowledgeItem] = []
    for order, r in enumerate(results):
        title = str(getattr(r, "title", "")).strip()
        url = str(getattr(r, "url", "")).strip()
        if not title or not url:
            continue
        snippet = str(getattr(r, "snippet", "")).strip()
        items.append(
            KnowledgeItem(
                source=SOURCE_SEARCH,
                item_id=url,
                content=f"{title} — {snippet}" if snippet else title,
                label=title,
                source_score=0.0,
                metadata={
                    "title": title,
                    "url": url,
                    "domain": str(getattr(r, "domain", "")),
                    "snippet": snippet,
                    "provider": str(getattr(r, "source", "")),
                    "order": order,
                },
            )
        )
    return items


async def _retrieve_memories(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    embedding_service: EmbeddingService,
    query_vector: list[float] | None,
    reinforce: bool,
) -> list[KnowledgeItem]:
    """Hybrid-retrieve memories, degrading to ``[]`` on any failure.

    No SAVEPOINT: the hybrid retriever commits its own reinforcement, which is
    incompatible with ``begin_nested``. Memory is the primary source and runs
    first, so a failure here is reported and the turn continues on goals + files.
    """
    try:
        ranked = await memory_retrieval_service.retrieve_memories(
            session,
            user_id=user_id,
            query=query,
            embedding_service=embedding_service,
            limit=KNOWLEDGE_MAX_MEMORIES,
            reinforce=reinforce,
            query_vector=query_vector,
        )
    except Exception as exc:
        logger.exception("knowledge: memory retrieval failed; degrading to none")
        capture_exception(exc, component="knowledge_retrieval", source=SOURCE_MEMORY)
        return []
    return [
        KnowledgeItem(
            source=SOURCE_MEMORY,
            item_id=str(item.memory.id),
            content=item.memory.content,
            label=item.memory.category.value,
            source_score=item.final_score,
            metadata={
                "category": item.memory.category.value,
                "semantic_similarity": item.semantic_similarity,
                "recency_score": item.recency_score,
                "importance_score": item.memory.importance_score,
                "confidence_score": item.memory.confidence_score,
            },
        )
        for item in ranked
    ]


async def _retrieve_goals(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[KnowledgeItem]:
    """Active goals, isolated in a SAVEPOINT and degrading to ``[]`` on failure."""
    active: list = []
    with langfuse_obs.observe_operation("knowledge.retrieve_goals") as span:
        try:
            async with session.begin_nested():
                active = await goal_repository.list_active(
                    session, user_id=user_id, limit=CONTEXT_MAX_GOALS
                )
        except Exception as exc:
            logger.exception("knowledge: goals lookup failed; degrading to none")
            capture_exception(exc, component="knowledge_retrieval", source=SOURCE_GOAL)
        span.update(metadata={"goals": len(active)})

    items: list[KnowledgeItem] = []
    for g in active:
        target = g.target_date.date().isoformat() if g.target_date else None
        items.append(
            KnowledgeItem(
                source=SOURCE_GOAL,
                item_id=str(g.id),
                content=g.title,
                label=g.title,
                # Filled by the ranker from priority + deadline.
                source_score=0.0,
                metadata={
                    "title": g.title,
                    "priority": g.priority.value,
                    "status": g.status.value,
                    "progress_percentage": g.progress_percentage,
                    "target_date": target,
                    # Raw datetime carried through for deadline-proximity math.
                    "_target_dt": g.target_date,
                },
            )
        )
    return items


async def _retrieve_files(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    attachment_file_ids: list[uuid.UUID] | None,
) -> tuple[list[KnowledgeItem], list[dict]]:
    """Retrieved file excerpts + inventory via ``file_context_service``.

    The search path degrades to ``([], [])`` on any failure (a files outage must
    never take a turn down); the attachment path lets exceptions propagate — a
    404 for a foreign/missing id is correct because the user explicitly
    referenced that file (a silent miss would be wrong, and is a tenancy signal).
    """
    if attachment_file_ids:
        ctx = await file_context_service.retrieve_file_context(
            session,
            user_id=user_id,
            query=query,
            attached_file_ids=attachment_file_ids,
        )
    else:
        try:
            ctx = await file_context_service.retrieve_file_context(
                session, user_id=user_id, query=query
            )
        except Exception as exc:
            logger.exception("knowledge: file retrieval failed; degrading to none")
            capture_exception(exc, component="knowledge_retrieval", source=SOURCE_FILE)
            return [], []
    attached = ctx.mode == "attachment"
    items: list[KnowledgeItem] = []
    for order, excerpt in enumerate(ctx.excerpts[:KNOWLEDGE_MAX_FILES]):
        items.append(
            KnowledgeItem(
                source=SOURCE_FILE,
                item_id=str(excerpt.file_id),
                content=excerpt.content[:KNOWLEDGE_FILE_CHUNK_CHAR_CAP],
                label=excerpt.filename,
                # Filled by the ranker from retrieval order + attachment boost.
                source_score=0.0,
                metadata={
                    "filename": excerpt.filename,
                    "chunk_index": excerpt.chunk_index,
                    "attached": attached,
                    "order": order,
                },
            )
        )
    return items, ctx.inventory


async def retrieve(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    embedding_service: EmbeddingService,
    attachment_file_ids: list[uuid.UUID] | None = None,
    query_vector: list[float] | None = None,
    reinforce: bool = True,
) -> UnifiedKnowledgeContext:
    """Retrieve from every knowledge source and attribute each item's origin.

    ``query_vector`` may be supplied by a caller that already embedded the query
    (so embedding can be timed separately). ``reinforce`` is forwarded to the
    memory retriever — diagnostics passes ``False`` to avoid mutating scores.

    Per-source failures degrade gracefully (see the module docstring); the only
    exception that propagates is a 404 from an explicit file attachment.
    """
    with langfuse_obs.observe_retrieval(
        "knowledge.retrieve",
        input=query,
        metadata={
            "has_attachments": bool(attachment_file_ids),
            "attachment_count": len(attachment_file_ids or []),
        },
    ) as span:
        memories = await _retrieve_memories(
            session,
            user_id=user_id,
            query=query,
            embedding_service=embedding_service,
            query_vector=query_vector,
            reinforce=reinforce,
        )
        goals = await _retrieve_goals(session, user_id=user_id)
        files, inventory = await _retrieve_files(
            session,
            user_id=user_id,
            query=query,
            attachment_file_ids=attachment_file_ids,
        )

        sources_used: list[str] = []
        if memories:
            sources_used.append(SOURCE_MEMORY)
        if goals:
            sources_used.append(SOURCE_GOAL)
        if files or inventory:
            sources_used.append(SOURCE_FILE)

        span.update(
            output={
                "memories": len(memories),
                "goals": len(goals),
                "files": len(files),
                "sources_used": sources_used,
            }
        )

    _emit_analytics(
        user_id=user_id,
        memories=len(memories),
        goals=len(goals),
        files=len(files),
        sources_used=sources_used,
        attachment_file_ids=attachment_file_ids,
    )

    return UnifiedKnowledgeContext(
        query=query,
        memories=memories,
        goals=goals,
        files=files,
        inventory=inventory,
        sources_used=sources_used,
        attachment_file_ids=list(attachment_file_ids or []),
    )


def context_from_pack(
    *,
    memories: list[dict],
    goals: list[dict],
    file_context: dict | None,
    query: str = "",
) -> UnifiedKnowledgeContext:
    """Adapt an agent ``ContextPack``'s data into a ``UnifiedKnowledgeContext``.

    The M8 consumption seam: an agent already handed a packed context (memories,
    goals, retrieved file content) reuses the *same* ranker + compressor as the
    chat core by mapping its pack into the unified shape — no re-retrieval, and a
    prompt identical to ``generate_grounded_reply``'s for the same inputs (the
    orchestration parity invariant). Pure: no I/O.
    """
    mem_items = [
        KnowledgeItem(
            source=SOURCE_MEMORY,
            item_id=str(i),
            content=str(m.get("content", "")),
            label=str(m.get("category", "")),
            source_score=float(m.get("score", 0.0)),
            metadata={"category": str(m.get("category", ""))},
        )
        for i, m in enumerate(memories)
    ]
    goal_items = [
        KnowledgeItem(
            source=SOURCE_GOAL,
            item_id=str(g.get("id", i)),
            content=str(g.get("title", "")),
            label=str(g.get("title", "")),
            source_score=0.0,
            metadata={
                "title": str(g.get("title", "")),
                "priority": str(g.get("priority", "medium")),
                "status": str(g.get("status", "active")),
                "progress_percentage": g.get("progress_percentage", 0),
                "target_date": g.get("target_date"),
                "_target_dt": _parse_dt(g.get("target_date")),
            },
        )
        for i, g in enumerate(goals)
    ]
    file_items: list[KnowledgeItem] = []
    inventory: list[dict] = []
    if isinstance(file_context, dict):
        inventory = file_context.get("inventory") or []
        excerpts = file_context.get("excerpts") or []
        for order, e in enumerate(excerpts[:KNOWLEDGE_MAX_FILES]):
            if not isinstance(e, dict):
                continue
            filename = str(e.get("filename", "file"))
            file_items.append(
                KnowledgeItem(
                    source=SOURCE_FILE,
                    item_id=filename,
                    content=str(e.get("content", ""))[:KNOWLEDGE_FILE_CHUNK_CHAR_CAP],
                    label=filename,
                    source_score=0.0,
                    metadata={"filename": filename, "order": order, "attached": False},
                )
            )

    sources_used: list[str] = []
    if mem_items:
        sources_used.append(SOURCE_MEMORY)
    if goal_items:
        sources_used.append(SOURCE_GOAL)
    if file_items or inventory:
        sources_used.append(SOURCE_FILE)

    return UnifiedKnowledgeContext(
        query=query,
        memories=mem_items,
        goals=goal_items,
        files=file_items,
        inventory=inventory,
        sources_used=sources_used,
    )


def _parse_dt(value: object):  # type: ignore[no-untyped-def]
    """Parse an ISO date/datetime string into a datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _emit_analytics(
    *,
    user_id: uuid.UUID,
    memories: int,
    goals: int,
    files: int,
    sources_used: list[str],
    attachment_file_ids: list[uuid.UUID] | None,
) -> None:
    """Emit the M7 analytics event family (best-effort; never raises)."""
    distinct_id = str(user_id)
    analytics.capture_event(
        distinct_id=distinct_id,
        event=analytics.EVENT_KNOWLEDGE_RETRIEVED,
        properties={
            "memories": memories,
            "goals": goals,
            "files": files,
            "sources_used": sources_used,
        },
    )
    for source in sources_used:
        analytics.capture_event(
            distinct_id=distinct_id,
            event=analytics.EVENT_KNOWLEDGE_SOURCE_USED,
            properties={"source": source},
        )
    if attachment_file_ids:
        analytics.capture_event(
            distinct_id=distinct_id,
            event=analytics.EVENT_KNOWLEDGE_ATTACHMENT_USED,
            properties={"attachment_count": len(attachment_file_ids)},
        )
