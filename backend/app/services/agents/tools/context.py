"""Execution context handed to Green tool executors.

Carries the tenant-scoped session and the services an executor may need.
Executors receive *only* this context + validated args — never the raw agent
output or any permission state (the prompt-injection boundary).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agents.tools.workspace import Workspace
from app.services.embeddings.embedding_service import EmbeddingService

# Deny-all workspace. This is the default rather than "read from settings"
# because the fallback for a context that forgot to carry one must be *no host
# access*, not whatever the environment happens to allow.
NO_WORKSPACE = Workspace(roots=())


@dataclass
class ToolContext:
    """Trusted per-invocation context for a tool executor."""

    session: AsyncSession
    user_id: uuid.UUID
    embedding_service: EmbeddingService | None = None
    # Which host directories the machine-facing tools (git, shell, host files)
    # may touch. Part of the trusted context precisely so it cannot arrive as a
    # tool argument: the model can choose a path, never the boundary.
    workspace: Workspace = NO_WORKSPACE
