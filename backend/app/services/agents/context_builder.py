"""Agent Context Builder — assemble the token-budgeted pack an agent gets.

A composition layer over the Phase 1/2 machinery: hybrid memory retrieval
(`memory_retrieval_service`) for ranked candidates, with thread history and
the rolling summary supplied by the caller (`run_turn` loads them *before*
appending the current user message, so the query never leaks into history —
the Phase 2 ordering preserved exactly). Token budgeting/dedupe stay in
`context_assembly_service`, applied by the handler at prompt time
(PHASE3_PLAN.md §8).
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    CONTEXT_MAX_FILES,
    CONTEXT_MAX_GOALS,
    CONTEXT_MAX_TASKS,
    DEFAULT_CONTEXT_MAX_MEMORIES,
)
from app.observability import langfuse as langfuse_obs
from app.repositories import file_repository, goal_repository, task_repository
from app.schemas.agents import ContextPack
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.memory import memory_retrieval_service

logger = logging.getLogger(__name__)


async def build(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    embedding_service: EmbeddingService,
    max_memories: int = DEFAULT_CONTEXT_MAX_MEMORIES,
    history: list[dict] | None = None,
    summary: str | None = None,
    scratch: list[dict] | None = None,
) -> ContextPack:
    """Build a scoped context pack for one agent dispatch.

    ``memories`` are the ranked retrieval candidates (content/category/score),
    exactly what the Phase 2 core feeds into context assembly. ``goals`` and
    ``tasks`` carry the user's active/open work state (M8) — pack **data**
    for agents that consume it; the general agent does not render them into
    its prompt in Phase 3, preserving reply parity with the legacy core.
    """
    ranked = await memory_retrieval_service.retrieve_memories(
        session,
        user_id=user_id,
        query=query,
        embedding_service=embedding_service,
        limit=max_memories,
    )
    memories = [
        {
            "content": item.memory.content,
            "category": item.memory.category.value,
            "score": item.final_score,
        }
        for item in ranked
    ]
    # Read access only (M5): exclusively *active* goals reach the agent —
    # completed and archived goals are intentionally never injected.
    #
    # Wrapped in a SAVEPOINT (``begin_nested``) + degrade-to-empty so a goal
    # outage (e.g. a DB schema behind the code) can never poison the turn's
    # transaction and take chat down. On PostgreSQL a failed statement aborts
    # the whole transaction; the savepoint confines the rollback to this lookup
    # so the agent still runs (without goals) and later writes still succeed.
    active_goals: list = []
    with langfuse_obs.observe_operation("goal.retrieve_active") as span:
        try:
            async with session.begin_nested():
                active_goals = await goal_repository.list_active(
                    session, user_id=user_id, limit=CONTEXT_MAX_GOALS
                )
        except Exception:
            logger.exception(
                "active-goals lookup failed; agent runs without goals"
            )
        span.update(metadata={"active_goals": len(active_goals)})
    open_tasks = await task_repository.list_open(
        session, user_id=user_id, limit=CONTEXT_MAX_TASKS
    )
    # Files awareness (M6): metadata only — the agent sees *what* the user has
    # uploaded, never the bytes. Same SAVEPOINT degrade-to-empty guard as goals
    # so a files-table outage can never take a turn down.
    recent_files: list = []
    with langfuse_obs.observe_operation("file.retrieve_recent") as span:
        try:
            async with session.begin_nested():
                recent_files = await file_repository.list_recent(
                    session, user_id=user_id, limit=CONTEXT_MAX_FILES
                )
        except Exception:
            logger.exception(
                "recent-files lookup failed; agent runs without files"
            )
        span.update(metadata={"recent_files": len(recent_files)})
    return ContextPack(
        memories=memories,
        history=list(history or []),
        summary=summary,
        goals=[
            {
                "id": str(g.id),
                "title": g.title,
                "status": g.status.value,
                "priority": g.priority.value,
                "category": g.category,
                "progress_percentage": g.progress_percentage,
                "target_date": (
                    g.target_date.isoformat() if g.target_date else None
                ),
                "milestones_total": len(g.milestones),
                "milestones_completed": sum(
                    1 for m in g.milestones if m.completed
                ),
                "agent_context": g.agent_context.value,
            }
            for g in active_goals
        ],
        tasks=[
            {
                "id": str(t.id),
                "title": t.title,
                "status": t.status.value,
                "agent_key": t.agent_key,
                "goal_id": str(t.goal_id) if t.goal_id else None,
            }
            for t in open_tasks
        ],
        files=[
            {
                "id": str(f.id),
                "filename": f.original_filename,
                "mime_type": f.mime_type,
                "processing_status": f.processing_status.value,
                "chunk_count": f.chunk_count,
            }
            for f in recent_files
        ],
        scratch=list(scratch or []),
    )
