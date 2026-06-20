"""Conversation turn service — one persistent, memory-grounded chat turn.

Orchestrates a turn end to end:

    load history → persist user msg → retrieve memories → assemble context (recent
    history + rolling summary + long-term memories) → prompt → LLM → persist
    assistant msg → update lifecycle → commit → enqueue enrichment (post-commit)

It reuses the existing memory pipeline (retrieval, context assembly, prompt
builder, LLM gateway) unchanged. ``generate_grounded_reply`` is the stateless reply
core; the persistent turn is ``run_turn``. This is the single memory-aware chat
entrypoint (the legacy stateless ``/chat`` route was retired in M8).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
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
from app.services.llm.base import LLMProvider, SupportsStreaming
from app.services.memory import (
    context_assembly_service,
    memory_retrieval_service,
    prompt_builder,
)
from app.services.memory.context_assembly_service import ContextMemory
from app.utils.tokens import estimate_tokens
from app.workers.enrichment_worker import enrichment_worker

logger = logging.getLogger(__name__)

# Roles that belong in the LLM message history (working memory).
_HISTORY_ROLES = (MessageRole.USER, MessageRole.ASSISTANT)


def _ms(start: float) -> float:
    """Elapsed milliseconds since a ``perf_counter`` start, rounded for logs."""
    return round((time.perf_counter() - start) * 1000, 1)


def _log_turn_timing(
    *,
    phase: str,
    conversation_id: uuid.UUID,
    timings: dict[str, float | None],
    memories_used: int,
) -> None:
    """Emit one structured timing line per turn (Railway-queryable fields).

    Surfaces where a turn spends its time — memory retrieval, embedding, prompt
    assembly, first-token, and full latency — without leaking any user content.
    """
    logger.info(
        "turn_timing",
        extra={
            "event": "turn_timing",
            "phase": phase,
            "conversation_id": str(conversation_id),
            "memories_used": memories_used,
            **{k: v for k, v in timings.items() if v is not None},
        },
    )


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
    identity: str | None = None,
    conversation_id: uuid.UUID | None = None,
) -> GeneratedReply:
    """Ground a reply in the user's memories (+ optional thread history/summary).

    Stateless: retrieves, assembles, prompts, and calls the LLM, but persists
    nothing and does not commit. Used by ``run_turn``. ``identity`` is the
    authenticated user-profile block, injected ahead of memory.
    """
    turn_start = time.perf_counter()

    embed_start = time.perf_counter()
    query_vector = await embedding_service.embed_query(message)
    embedding_ms = _ms(embed_start)

    retrieve_start = time.perf_counter()
    ranked = await memory_retrieval_service.retrieve_memories(
        session,
        user_id=user_id,
        query=message,
        embedding_service=embedding_service,
        limit=max_memories,
        query_vector=query_vector,
    )
    retrieve_memories_ms = _ms(retrieve_start)

    prompt_start = time.perf_counter()
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
        context=package,
        query=message,
        history=history,
        summary=summary,
        identity=identity,
    )
    prompt_build_ms = _ms(prompt_start)

    llm_start = time.perf_counter()
    response = await llm.generate(system=payload.system, messages=payload.messages)
    first_token_ms = _ms(llm_start)

    _log_turn_timing(
        phase="generate",
        conversation_id=conversation_id or uuid.UUID(int=0),
        timings={
            "embedding_ms": embedding_ms,
            "retrieve_memories_ms": retrieve_memories_ms,
            "prompt_build_ms": prompt_build_ms,
            "first_token_ms": first_token_ms,
            "total_turn_ms": _ms(turn_start),
        },
        memories_used=len(package.memories),
    )
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
    identity: str | None = None,
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
    # First turn → generate the thread title inline (below), so it lands with
    # this turn's commit and is visible the instant the client refetches.
    is_first_turn = not prior

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

    # Phase 3 (flag-gated; lazy imports keep the conversation domain free of
    # a module-level agents dependency):
    #   - agents_orchestration_enabled (M4): delegate the reply to the Master
    #     Orchestrator with a guaranteed fallback to the legacy core — an
    #     orchestrator error never costs the user a reply.
    #   - agents_run_recording (M3): trace the unchanged legacy call as a
    #     single-agent run. Behavior byte-identical.
    # All trace rows are flush-only and commit atomically with the messages.
    settings = get_settings()
    proposed_memories: list[dict] = []
    if settings.agents_orchestration_enabled:
        from app.services.agents import orchestrator_service

        try:
            orch = await orchestrator_service.orchestrate(
                session,
                user_id=user_id,
                conversation_id=conversation_id,
                message=message,
                embedding_service=embedding_service,
                llm=llm,
                token_budget=token_budget,
                max_memories=max_memories,
                history=history,
                summary=summary_text,
                agent_context=conversation.agent_context,
                user_identity=identity,
            )
            reply = GeneratedReply(
                reply=orch.reply,
                model=orch.model,
                memories_used=orch.memories_used,
                input_tokens=orch.input_tokens,
                output_tokens=orch.output_tokens,
            )
            proposed_memories = orch.proposed_memories
        except Exception:
            logger.exception(
                "orchestrator failed; falling back to the legacy reply core"
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
                identity=identity,
                conversation_id=conversation_id,
            )
    elif settings.agents_run_recording:
        from app.services.agents import run_recorder
        from app.services.agents.manifests import GENERAL_AGENT_KEY

        recording = await run_recorder.start_run(
            session,
            user_id=user_id,
            agent_key=GENERAL_AGENT_KEY,
            conversation_id=conversation_id,
            input={"message_preview": message[:200]},
        )
        try:
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
                identity=identity,
                conversation_id=conversation_id,
            )
        except Exception as exc:
            # Flush-only; without a commit the trace vanishes with the
            # rollback — behavior stays identical to the unrecorded path.
            await run_recorder.finish_failure(
                session, recording, error=str(exc)
            )
            raise
        await run_recorder.finish_success(
            session,
            recording,
            output={
                "reply_preview": reply.reply[:200],
                "model": reply.model,
                "memories_used": reply.memories_used,
            },
            cost_tokens=reply.input_tokens + reply.output_tokens,
        )
    else:
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
            identity=identity,
            conversation_id=conversation_id,
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

    # First turn: title the thread from the opening message inline, so it
    # commits with this turn and the client sees it on its post-turn refetch
    # (instead of lagging behind the background enrichment worker). Best-effort
    # — a title failure must never cost the user their reply; the enrichment
    # worker's idempotent backfill remains the fallback.
    if is_first_turn:
        try:
            await conversation_service.backfill_title(
                session,
                user_id=user_id,
                conversation_id=conversation_id,
                llm=llm,
            )
        except Exception:
            logger.exception(
                "inline title generation failed; worker will retry"
            )

    await session.commit()
    await session.refresh(assistant_message)

    # Post-commit, off the request path: the background worker runs the
    # enrichment consumers (title backfill + rolling summary; extraction is an
    # M6 stub). No-op when the worker is idle (e.g. in unit tests).
    enrichment_worker.enqueue(conversation_id, user_id)

    # Phase 3 M7 (post-commit, best-effort): persist agent-proposed memories
    # through the consent gate + Memory Engine + 'agent' provenance. Runs
    # after the turn's unit of work because memory_service owns its own
    # commit; a failure here must never cost the user their reply.
    if proposed_memories:
        from app.services.agents import agent_memory

        try:
            await agent_memory.propose(
                session,
                user_id=user_id,
                candidates=proposed_memories,
                agent_key="orchestrator",
                conversation_id=conversation_id,
            )
        except Exception:
            logger.exception("agent memory proposal failed; reply unaffected")

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


async def stream_turn(
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
    identity: str | None = None,
) -> AsyncIterator[dict]:
    """Run a memory-grounded turn, streaming the reply as it is generated.

    Yields event dicts: ``{"type": "delta", "text": ...}`` per chunk, then a
    terminal ``{"type": "done", ...}`` with persisted ids/metadata. Persistence
    (user + assistant messages, lifecycle, title, enrichment dispatch) happens
    after the stream completes, mirroring ``run_turn``'s unit of work.

    This is the grounded reply core (no orchestration) so it can stream a single
    LLM call. Providers without streaming fall back to one ``generate`` call
    whose full text is emitted as a single delta.
    """
    turn_start = time.perf_counter()
    conversation = await conversation_service.get_conversation(
        session, user_id=user_id, conversation_id=conversation_id
    )

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
    is_first_turn = not prior

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

    # Build the grounded prompt (same pipeline as generate_grounded_reply).
    # Embedding is timed separately from candidate retrieval/ranking by
    # pre-embedding the query and handing the vector to the retriever.
    embed_start = time.perf_counter()
    query_vector = await embedding_service.embed_query(message)
    embedding_ms = _ms(embed_start)

    retrieve_start = time.perf_counter()
    ranked = await memory_retrieval_service.retrieve_memories(
        session,
        user_id=user_id,
        query=message,
        embedding_service=embedding_service,
        limit=max_memories,
        query_vector=query_vector,
    )
    retrieve_memories_ms = _ms(retrieve_start)

    prompt_start = time.perf_counter()
    candidates = [
        ContextMemory(
            content=item.memory.content,
            category=item.memory.category.value,
            score=item.final_score,
        )
        for item in ranked
    ]
    package = context_assembly_service.assemble_context(
        candidates, token_budget=token_budget, max_memories=max_memories
    )
    payload = prompt_builder.build_prompt(
        context=package,
        query=message,
        history=history,
        summary=summary_text,
        identity=identity,
    )
    prompt_build_ms = _ms(prompt_start)

    # Stream the reply, accumulating the full text for persistence. Record the
    # latency to the FIRST emitted token — the metric that drives perceived speed.
    chunks: list[str] = []
    llm_start = time.perf_counter()
    first_token_ms: float | None = None
    if isinstance(llm, SupportsStreaming):
        async for chunk in llm.stream(
            system=payload.system, messages=payload.messages
        ):
            if first_token_ms is None:
                first_token_ms = _ms(llm_start)
            chunks.append(chunk)
            yield {"type": "delta", "text": chunk}
        model = getattr(llm, "_default_model", llm.name)
    else:
        response = await llm.generate(
            system=payload.system, messages=payload.messages
        )
        first_token_ms = _ms(llm_start)
        chunks.append(response.text)
        model = response.model
        yield {"type": "delta", "text": response.text}

    _log_turn_timing(
        phase="stream",
        conversation_id=conversation_id,
        timings={
            "embedding_ms": embedding_ms,
            "retrieve_memories_ms": retrieve_memories_ms,
            "prompt_build_ms": prompt_build_ms,
            "first_token_ms": first_token_ms,
            "total_turn_ms": _ms(turn_start),
        },
        memories_used=len(package.memories),
    )

    reply_text = "".join(chunks)

    assistant_message = await msg_repo.append_message(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        role=MessageRole.ASSISTANT,
        content=reply_text,
        token_count=estimate_tokens(reply_text),
        model=model,
        input_tokens=estimate_tokens(payload.system),
        output_tokens=estimate_tokens(reply_text),
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

    if is_first_turn:
        try:
            await conversation_service.backfill_title(
                session,
                user_id=user_id,
                conversation_id=conversation_id,
                llm=llm,
            )
        except Exception:
            logger.exception("inline title generation failed; worker will retry")

    await session.commit()

    enrichment_worker.enqueue(conversation_id, user_id)

    yield {
        "type": "done",
        "conversation_id": str(conversation_id),
        "user_message_id": str(user_message.id),
        "assistant_message_id": str(assistant_message.id),
        "model": model,
        "memories_used": len(package.memories),
        # Short contents of the grounding memories so the client can show a
        # "Memory Used" disclosure (never the embeddings/scores — just the fact).
        "memories": [m.content for m in package.memories],
        "message_count": message_count,
    }
