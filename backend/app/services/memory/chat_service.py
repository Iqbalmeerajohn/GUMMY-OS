"""Memory-aware chat service — compatibility shim (Phase 2, M4).

The stateless, non-persisting "memory-grounded reply" path that backs the legacy
``/api/v1/chat`` endpoint. As of M4 its logic lives in
``conversation_turn_service.generate_grounded_reply`` (shared with the persistent
turn); this module is a thin wrapper that preserves the original ``chat()``
signature and ``ChatResult`` shape so existing callers/tests are unchanged.

The persistent, thread-based turn is ``conversation_turn_service.run_turn``. This
shim is slated for retirement in M8 once the conversation turn endpoint supersedes
the stateless ``/chat`` route.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    DEFAULT_CONTEXT_MAX_MEMORIES,
    DEFAULT_CONTEXT_TOKEN_BUDGET,
)
from app.services.conversation import conversation_turn_service
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.llm.base import LLMProvider


@dataclass(frozen=True)
class ChatResult:
    """The outcome of a chat turn."""

    reply: str
    model: str
    memories_used: int
    input_tokens: int
    output_tokens: int


async def chat(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    message: str,
    embedding_service: EmbeddingService,
    llm: LLMProvider,
    token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET,
    max_memories: int = DEFAULT_CONTEXT_MAX_MEMORIES,
) -> ChatResult:
    """Answer a user message grounded in their memories (stateless, no persistence).

    Delegates to the shared reply core in ``conversation_turn_service``.
    """
    reply = await conversation_turn_service.generate_grounded_reply(
        session,
        user_id=user_id,
        message=message,
        embedding_service=embedding_service,
        llm=llm,
        token_budget=token_budget,
        max_memories=max_memories,
    )
    return ChatResult(
        reply=reply.reply,
        model=reply.model,
        memories_used=reply.memories_used,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
    )
