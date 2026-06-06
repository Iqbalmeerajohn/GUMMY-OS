"""Memory-aware chat service.

Orchestrates one chat turn end to end:

    user query → hybrid retrieval → context assembly → prompt builder → LLM → reply

No reasoning logic of its own — it wires the existing layers together and returns
a normalized result. (No RAG, agents, or orchestration here — just this pipeline.)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    DEFAULT_CONTEXT_MAX_MEMORIES,
    DEFAULT_CONTEXT_TOKEN_BUDGET,
)
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.llm.base import LLMProvider
from app.services.memory import (
    context_assembly_service,
    memory_retrieval_service,
    prompt_builder,
)
from app.services.memory.context_assembly_service import ContextMemory


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
    """Answer a user message grounded in their retrieved memories."""
    ranked = await memory_retrieval_service.retrieve_memories(
        session,
        user_id=user_id,
        query=message,
        embedding_service=embedding_service,
        limit=max_memories,
    )

    candidates = [
        ContextMemory(
            content=item.memory.content,
            category=item.memory.category.value,
            score=item.final_score,
        )
        for item in ranked
    ]
    package = context_assembly_service.assemble_context(
        candidates,
        token_budget=token_budget,
        max_memories=max_memories,
    )

    payload = prompt_builder.build_prompt(context=package, query=message)
    response = await llm.generate(
        system=payload.system,
        messages=payload.messages,
    )

    return ChatResult(
        reply=response.text,
        model=response.model,
        memories_used=len(package.memories),
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )
