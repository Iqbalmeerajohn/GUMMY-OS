"""Aggregate router for versioned endpoints, mounted under ``/api/v1``.

Phase 1 routers are included here as they are built, e.g.::

    from app.api.v1 import memories, retrieval, documents, resumes

    api_router.include_router(memories.router)
    api_router.include_router(retrieval.router)
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    actions,
    agents,
    conversations,
    files,
    goals,
    knowledge,
    memories,
    milestones,
    tasks,
)

api_router = APIRouter()
api_router.include_router(memories.router)
api_router.include_router(conversations.router)
api_router.include_router(goals.router)
api_router.include_router(milestones.router)
api_router.include_router(tasks.router)
api_router.include_router(actions.router)
api_router.include_router(files.router)
api_router.include_router(knowledge.router)
api_router.include_router(agents.router)
