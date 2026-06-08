"""Conversation turn service — one persistent, memory-grounded chat turn.

Orchestrates a turn end to end:

    load history → persist user msg → retrieve memories → assemble context →
    prompt → LLM → persist assistant msg → update lifecycle → commit →
    dispatch enrichment (post-commit, no-op consumers in M4)

It reuses the existing memory pipeline (retrieval, context assembly, prompt
builder, LLM gateway) unchanged. The stateless ``generate_grounded_reply`` core is
shared with the legacy ``chat_service`` shim. No summaries, extraction, retrieval
tuning, or search here — those are later milestones (PHASE2_PLAN.md §2/§8).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    DEFAULT_CONTEXT_MAX_MEMORIES,
    DEFAULT_CONTEXT_TOKEN_BUDGET,
    DEFAULT_TURN_HISTORY_MESSAGES,
)
from app.models.enums import MessageRole, SummaryType
from app.repositories import conversation_repository as conv_repo
from app.repositories import conversation_summary_repository as sum_repo
from app.repositories import message_repository as msg_repo
from app.services.conversation import conversation_service
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.llm.base import LLMProvider
from app.services.memory import (
    context_assembly_service,
    memory_retrieval_service,
    prompt_builder,
)
from app.services.memory.context_assembly_service import ContextMemory
from app.utils.tokens import estimate_tokens
from app.workers.enrichment_worker import enrichment_worker

# Roles that belong in the LLM message history (working memory).
_HISTORY_ROLES = (MessageRole.USER, MessageRole.ASSISTANT)


@dataclass(frozen=True)
class GeneratedReply:
    """The stateless outcome of grounding a reply in memory (no persistence)."""

    reply: str
    model: str
    memories_used: int
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class TurnResult:
    """The outcome of a persisted conversation turn."""

    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    reply: str
    model: str
    memories_used: int
    input_tokens: int
    output_tokens: int
    message_count: int


async def generate_grounded_reply(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    message: str,
    embedding_service: EmbeddingService,
    llm: LLMProvider,
    token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET,
    max_memories: int = DEFAULT_CONTEXT_MAX_MEMORIES,
    history: list[dict[str, str]] | None = None,
    summary: str | None = None,
) -> GeneratedReply:
    """Ground a reply in the user's memories (+ optional thread history/summary).

    Stateless: retrieves, assembles, prompts, and calls the LLM, but persists
    nothing and does not commit. Shared by the turn flow and the chat shim.
    """
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
    payload = prompt_builder.build_prompt(
        context=package, query=message, history=history, summary=summary
    )
    response = await llm.generate(system=payload.system, messages=payload.messages)
    return GeneratedReply(
        reply=response.text,
        model=response.model,
        memories_used=len(package.memories),
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )


async def run_turn(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message: str,
    embedding_service: EmbeddingService,
    llm: LLMProvider,
    token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET,
    max_memories: int = DEFAULT_CONTEXT_MAX_MEMORIES,
    history_limit: int = DEFAULT_TURN_HISTORY_MESSAGES,
) -> TurnResult:
    """Run one persisted, memory-grounded turn in a conversation.

    Persists the user message and the assistant reply, bumps the conversation's
    recency + counter, commits, then dispatches enrichment (no-op consumers in
    M4). Raises 404 if the conversation is not the tenant's.
    """
    conversation = await conversation_service.get_conversation(
        session, user_id=user_id, conversation_id=conversation_id
    )

    # Recent PRIOR turns as working memory (loaded before appending the current
    # message, so the new user message is the query, not part of history).
    prior = await msg_repo.recent_messages(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        limit=history_limit,
    )
    history = [
        {"role": m.role.value, "content": m.content}
        for m in prior
        if m.role in _HISTORY_ROLES
    ]

    # Rolling summary = compressed older context (None until M5 produces one).
    rolling = await sum_repo.latest_summary(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        summary_type=SummaryType.ROLLING,
    )
    summary_text = rolling.content if rolling is not None else None

    user_message = await msg_repo.append_message(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        role=MessageRole.USER,
        content=message,
        token_count=estimate_tokens(message),
    )

    reply = await generate_grounded_reply(
        session,
        user_id=user_id,
        message=message,
        embedding_service=embedding_service,
        llm=llm,
        token_budget=token_budget,
        max_memories=max_memories,
        history=history,
        summary=summary_text,
    )

    assistant_message = await msg_repo.append_message(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        role=MessageRole.ASSISTANT,
        content=reply.reply,
        token_count=reply.output_tokens,
        model=reply.model,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
    )

    message_count = await msg_repo.count_messages(
        session, conversation_id=conversation_id, user_id=user_id
    )
    await conv_repo.touch_last_message(
        session,
        conversation,
        last_message_at=datetime.now(UTC),
        message_count=message_count,
    )

    await session.commit()
    await session.refresh(assistant_message)

    # Post-commit, off the request path: the background worker runs the
    # enrichment consumers (title backfill + rolling summary; extraction is an
    # M6 stub). No-op when the worker is idle (e.g. in unit tests).
    enrichment_worker.enqueue(conversation_id, user_id)

    return TurnResult(
        conversation_id=conversation_id,
        user_message_id=user_message.id,
        assistant_message_id=assistant_message.id,
        reply=reply.reply,
        model=reply.model,
        memories_used=reply.memories_used,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
        message_count=message_count,
    )
