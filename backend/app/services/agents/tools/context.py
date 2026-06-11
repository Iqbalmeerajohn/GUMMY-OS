"""Execution context handed to Green tool executors.

Carries the tenant-scoped session and the services an executor may need.
Executors receive *only* this context + validated args — never the raw agent
output or any permission state (the prompt-injection boundary).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embeddings.embedding_service import EmbeddingService


@dataclass
class ToolContext:
    """Trusted per-invocation context for a tool executor."""

    session: AsyncSession
    user_id: uuid.UUID
    embedding_service: EmbeddingService | None = None
