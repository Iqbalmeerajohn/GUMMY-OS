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

import dataclasses
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
from app.core.observability import capture_exception
from app.models.conversation import Conversation
from app.models.enums import AgentContext, MessageRole, SummaryType
from app.models.message import Message
from app.repositories import conversation_repository as conv_repo
from app.repositories import conversation_summary_repository as sum_repo
from app.repositories import message_repository as msg_repo
from app.schemas.goal import GoalCandidate
from app.services.conversation import (
    conversation_continuity_service,
    conversation_service,
    emotion,
)
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.goals import goal_extraction_service
from app.services.knowledge import (
    knowledge_context_builder,
    knowledge_ranker,
    knowledge_retrieval_service,
)
from app.services.knowledge.knowledge_context_builder import CompiledKnowledge
from app.services.llm.base import LLMProvider, SupportsStreaming
from app.services.memory import (
    instant_recall,
    prompt_builder,
    timeline,
    user_profile_service,
)
from app.services.memory.context_assembly_service import ContextPackage
from app.services.search import search_service
from app.utils.tokens import estimate_tokens
from app.workers.enrichment_worker import enrichment_worker

logger = logging.getLogger(__name__)

# Roles that belong in the LLM message history (working memory).
_HISTORY_ROLES = (MessageRole.USER, MessageRole.ASSISTANT)

# The unified knowledge path renders its own ``<knowledge>`` block, so the legacy
# ``<memory>`` block is empty — build_prompt skips it when ``knowledge`` is set.
_EMPTY_CONTEXT = ContextPackage(memories=[], token_estimate=0)

# Recorded as the "model" for instant-recall replies. A real model name would be
# a lie in the message history and in cost accounting, since none was called.
_INSTANT_MODEL = "gummy-instant-recall"


async def _build_knowledge(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    message: str,
    embedding_service: EmbeddingService,
    attachment_file_ids: list[uuid.UUID] | None,
    query_vector: list[float] | None,
    agent_key: str | None = None,
) -> tuple[CompiledKnowledge, list[dict]]:
    """Retrieve → (fuse search) → rank → compress into one prompt block (M7/M8.5).

    The Unified Knowledge Engine fuses memories, goals, and files into a single
    ranked, token-budgeted ``<knowledge>`` block. Per-source failures degrade
    gracefully inside the engine (no source can take down a turn); only an
    explicit file-attachment 404 propagates.

    ``agent_key`` (M8.5) enables supplemental live web search for the eligible
    specialists when the query is search-worthy; the gate + provider are
    best-effort, so an ineligible/disabled/failed search just adds nothing.
    Returns the compiled block plus the compact web sources used (for the UI).
    """
    ctx = await knowledge_retrieval_service.retrieve(
        session,
        user_id=user_id,
        query=message,
        embedding_service=embedding_service,
        attachment_file_ids=attachment_file_ids,
        query_vector=query_vector,
    )
    web_sources: list[dict] = []
    web_results = await search_service.maybe_search(agent_key, message, user_id=user_id)
    if web_results:
        search_items = knowledge_retrieval_service.search_items_from_results(
            web_results
        )
        ctx = dataclasses.replace(ctx, search=search_items)
        web_sources = [
            {
                "title": str(i.metadata.get("title", i.label)),
                "url": str(i.metadata.get("url", "")),
                "domain": str(i.metadata.get("domain", "")),
            }
            for i in search_items
        ]
    ranked = knowledge_ranker.rank(ctx)
    compiled = knowledge_context_builder.build(ranked, inventory=ctx.inventory)
    return compiled, web_sources


def _detect_goal_candidate(message: str) -> GoalCandidate | None:
    """Detect a goal candidate in the user message (M5.5), defensively.

    Deterministic and cheap (no LLM), so it runs inline on the turn. Detection
    only *proposes* a goal — creation requires explicit user confirmation. Any
    failure is swallowed so it can never break a turn."""
    try:
        return goal_extraction_service.detect_goal(message)
    except Exception:
        logger.exception("goal detection failed; turn unaffected")
        return None


async def _select_stream_agent(
    *,
    message: str,
    agent_context: AgentContext | None,
    agent_key: str | None,
    knowledge_block: str,
    llm: LLMProvider,
) -> tuple[str | None, dict | None, str]:
    """Route a streamed turn to an agent and resolve its persona (M8).

    Mirrors the orchestrated path's routing for the streaming core: the
    deterministic keyword Router (free; no LLM by default) picks the agent, and
    the specialist's persona is prepended to the system prompt so the streamed
    reply speaks in the right voice. Returns
    ``(selected_agent, assistant_metadata, persona)``; a no-op
    ``(None, None, "")`` when orchestration is disabled, leaving the legacy
    stream byte-identical. Best-effort — any routing fault degrades to the
    general grounded stream so a reply is never lost.
    """
    settings = get_settings()
    if not settings.agents_orchestration_enabled:
        return None, None, ""
    try:
        # Lazy imports keep the conversation domain free of a module-level
        # agents dependency (same pattern as run_turn's orchestration branch).
        from app.services.agents import router as agent_router
        from app.services.agents.manifests import GENERAL_AGENT_KEY
        from app.services.agents.prompts import PERSONA_BUILDERS
        from app.services.agents.prompts.formatting import FORMATTING_RULES
        from app.services.agents.registry import get_registry

        decision = await agent_router.route(
            intent=message,
            registry=get_registry(),
            agent_context=agent_context,
            forced_agent_key=agent_key,
            llm=llm if settings.agents_router_llm_fallback else None,
            fast_model=settings.claude_model_fast,
        )
        selected_agent = decision.steps[-1].agent_key
        persona = ""
        persona_fn = PERSONA_BUILDERS.get(selected_agent)
        if persona_fn is not None and selected_agent != GENERAL_AGENT_KEY:
            persona = persona_fn(message, knowledge_block)
        # The non-streamed specialist handler prepends FORMATTING_RULES; this
        # path did not, so streamed replies could emit markdown tables that the
        # incremental renderer cannot display correctly. Every reply the user
        # actually sees comes through here, so the rules belong on this path
        # more than on the one they were written for.
        persona = f"{persona}\n\n{FORMATTING_RULES}" if persona else FORMATTING_RULES
        metadata = {
            "agent_key": selected_agent,
            "route_shape": decision.plan_shape.value,
            # A5: persist the routing explanation on the streamed reply too.
            "confidence": decision.confidence,
            "routing_reason": decision.rationale,
        }
        return selected_agent, metadata, persona
    except Exception:
        logger.exception("stream agent routing failed; streaming general reply")
        return None, None, ""


def _emit_stream_route_analytics(
    *, user_id: uuid.UUID, selected_agent: str, overridden: bool
) -> None:
    """Emit ``AgentSelected`` (+ ``AgentOverride``) for a streamed turn.

    Best-effort and lazy-imported; ``capture_event`` never raises, so analytics
    can never break a stream.
    """
    try:
        from app.observability import analytics

        analytics.capture_event(
            distinct_id=str(user_id),
            event=analytics.EVENT_AGENT_SELECTED,
            properties={"agent": selected_agent, "overridden": overridden},
        )
        if overridden:
            analytics.capture_event(
                distinct_id=str(user_id),
                event=analytics.EVENT_AGENT_OVERRIDE,
                properties={"agent": selected_agent},
            )
    except Exception:
        logger.debug("stream route analytics failed", exc_info=True)


def _ms(start: float) -> float:
    """Elapsed milliseconds since a ``perf_counter`` start, rounded for logs."""
    return round((time.perf_counter() - start) * 1000, 1)


async def _personalize(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    message: str,
    identity: str | None,
) -> str | None:
    """Fold everything GUMMY knows about *the person* into one prompt block.

    Three things happen here, in one place because they share the same slot in
    the prompt and the same failure policy:

    * the learned profile is updated with this message and rendered, so the
      portrait is current before the reply that uses it;
    * a retrospective question ("what did I do last week") pulls the episodic
      timeline, which similarity search cannot answer;
    * the message's emotional register becomes a delivery instruction.

    Entirely best-effort. Personalization improves a reply; it must never be the
    reason there isn't one, so any failure degrades to the plain identity block.
    """
    blocks: list[str | None] = [identity]
    reading = emotion.detect(message)

    try:
        profile = await user_profile_service.observe(
            session, user_id=user_id, message=message, mood=reading
        )
        blocks.append(user_profile_service.render(profile))
    except Exception:
        logger.exception("profile observation failed; continuing without it")

    try:
        window = timeline.detect_window(message)
        if window is not None:
            events = await timeline.events(session, user_id=user_id, window=window)
            blocks.append(timeline.render(window, events))
    except Exception:
        logger.exception("timeline lookup failed; continuing without it")

    blocks.append(emotion.tone_directive(reading))
    merged = "\n\n".join(b for b in blocks if b)
    return merged or None


async def _try_instant_recall(
    session: AsyncSession, *, user_id: uuid.UUID, message: str
) -> instant_recall.InstantAnswer | None:
    """Attempt a no-LLM answer, defensively.

    Any failure here degrades to the normal grounded reply, so a bug in the fast
    path can cost latency but never a reply.
    """
    try:
        return await instant_recall.try_answer(
            session, user_id=user_id, message=message
        )
    except Exception:
        logger.exception("instant recall failed; falling through to the model")
        return None


async def _finish_instant_turn(
    session: AsyncSession,
    *,
    conversation: Conversation,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user_message: Message,
    answer: instant_recall.InstantAnswer,
    turn_start: float,
    is_first_turn: bool,
    llm: LLMProvider,
) -> AsyncIterator[dict]:
    """Persist and emit an instant-recall turn in the normal stream shape.

    Emits the same ``delta`` → ``done`` sequence as a generated turn so the
    client needs no special case: from the UI's perspective this is simply a
    very fast reply.
    """
    yield {"type": "delta", "text": answer.text}

    assistant_message = await msg_repo.append_message(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        role=MessageRole.ASSISTANT,
        content=answer.text,
        token_count=estimate_tokens(answer.text),
        model=_INSTANT_MODEL,
        input_tokens=0,
        output_tokens=0,
        extra_metadata={
            "agent_key": "recall",
            "instant_recall": True,
            "intent": answer.intent_key,
            "confidence": answer.confidence,
        },
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
                session, user_id=user_id, conversation_id=conversation_id, llm=llm
            )
        except Exception:
            logger.exception("inline title generation failed; worker will retry")

    await session.commit()
    enrichment_worker.enqueue(conversation_id, user_id)

    _log_turn_timing(
        phase="instant",
        conversation_id=conversation_id,
        timings={"first_token_ms": _ms(turn_start), "total_turn_ms": _ms(turn_start)},
        memories_used=1,
    )

    yield {
        "type": "done",
        "conversation_id": str(conversation_id),
        "user_message_id": str(user_message.id),
        "assistant_message_id": str(assistant_message.id),
        "model": _INSTANT_MODEL,
        "memories_used": 1,
        "memories": [answer.text],
        "message_count": message_count,
        "agent": "recall",
        "web_sources": [],
        "goal_candidate": None,
    }


def _log_turn_timing(
    *,
    phase: str,
    conversation_id: uuid.UUID,
    timings: dict[str, float | None],
    memories_used: int,
) -> None:
    """Emit one structured timing line per turn (queryable log fields).

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
    # A goal-like statement detected in the user's message (M5.5), surfaced for
    # explicit confirmation. ``None`` when the message isn't goal-shaped.
    goal_candidate: GoalCandidate | None = None


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
    attachment_file_ids: list[uuid.UUID] | None = None,
) -> GeneratedReply:
    """Ground a reply in the user's memories (+ optional thread history/summary).

    Stateless: retrieves, assembles, prompts, and calls the LLM, but persists
    nothing and does not commit. Used by ``run_turn``. ``identity`` is the
    authenticated user-profile block, injected ahead of memory.
    ``attachment_file_ids`` (M6.5) scopes file grounding to attached files;
    otherwise relevant file chunks are keyword-retrieved across the user's files.
    """
    turn_start = time.perf_counter()

    embed_start = time.perf_counter()
    query_vector = await embedding_service.embed_query(message)
    embedding_ms = _ms(embed_start)

    retrieve_start = time.perf_counter()
    # Legacy/general reply core: no specialist routing here, so search stays off
    # (agent_key=None → no fusion). The orchestrated + streamed paths carry the
    # agent and own search fusion.
    knowledge, _web_sources = await _build_knowledge(
        session,
        user_id=user_id,
        message=message,
        embedding_service=embedding_service,
        attachment_file_ids=attachment_file_ids,
        query_vector=query_vector,
    )
    retrieve_memories_ms = _ms(retrieve_start)

    prompt_start = time.perf_counter()
    prior_context = await conversation_continuity_service.gather_prior_context(
        session,
        user_id=user_id,
        message=message,
        embedding_service=embedding_service,
        current_conversation_id=conversation_id,
    )
    payload = prompt_builder.build_prompt(
        context=_EMPTY_CONTEXT,
        query=message,
        history=history,
        summary=summary,
        identity=identity,
        prior_context=prior_context,
        knowledge=knowledge.block,
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
        memories_used=knowledge.memories_used,
    )
    return GeneratedReply(
        reply=response.text,
        model=response.model,
        memories_used=knowledge.memories_used,
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
    attachment_file_ids: list[uuid.UUID] | None = None,
    agent_key: str | None = None,
) -> TurnResult:
    """Run one persisted, memory-grounded turn in a conversation.

    Persists the user message and the assistant reply, bumps the conversation's
    recency + counter, commits, then dispatches enrichment (no-op consumers in
    M4). Raises 404 if the conversation is not the tenant's. ``agent_key`` (M8)
    is the manual agent override forwarded to the orchestrator; ``None`` lets the
    Router decide (Auto).
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

    identity = await _personalize(
        session, user_id=user_id, message=message, identity=identity
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
    # M8: the agent that answered + run trace ids, persisted on the assistant
    # message so the client can badge which agent replied. ``None`` on the
    # legacy/fallback paths (no orchestrated route to attribute).
    assistant_metadata: dict | None = None

    # Fast path first, exactly as in the streamed turn: a direct question about a
    # fact Gummy already stores is answered from memory with no model call, no
    # embedding, and no retrieval. Declines cheaply and falls through.
    instant = await _try_instant_recall(session, user_id=user_id, message=message)
    if instant is not None:
        reply = GeneratedReply(
            reply=instant.text,
            model=_INSTANT_MODEL,
            memories_used=1,
            input_tokens=0,
            output_tokens=0,
        )
        assistant_metadata = {
            "agent_key": "recall",
            "instant_recall": True,
            "intent": instant.intent_key,
            "confidence": instant.confidence,
        }
    elif settings.agents_orchestration_enabled:
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
                agent_key=agent_key,
                user_identity=identity,
                attachment_file_ids=attachment_file_ids,
            )
            reply = GeneratedReply(
                reply=orch.reply,
                model=orch.model,
                memories_used=orch.memories_used,
                input_tokens=orch.input_tokens,
                output_tokens=orch.output_tokens,
            )
            proposed_memories = orch.proposed_memories
            assistant_metadata = orch.message_metadata
        except Exception as exc:
            logger.exception(
                "orchestrator failed; falling back to the legacy reply core"
            )
            # The user still gets a reply via the fallback below, so this is
            # swallowed — report it so orchestration regressions are visible.
            capture_exception(
                exc,
                component="agent_orchestration",
                conversation_id=str(conversation_id),
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
                attachment_file_ids=attachment_file_ids,
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
                attachment_file_ids=attachment_file_ids,
            )
        except Exception as exc:
            # Flush-only; without a commit the trace vanishes with the
            # rollback — behavior stays identical to the unrecorded path.
            await run_recorder.finish_failure(session, recording, error=str(exc))
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
            attachment_file_ids=attachment_file_ids,
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
        extra_metadata=assistant_metadata,
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
            logger.exception("inline title generation failed; worker will retry")

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
        # Goal Intelligence (M5.5): surface a detected goal candidate (if any)
        # for the client to offer creation. Never auto-created.
        goal_candidate=_detect_goal_candidate(message),
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
    attachment_file_ids: list[uuid.UUID] | None = None,
    agent_key: str | None = None,
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

    # Before the fast path, so the learned profile counts every turn — including
    # the ones answered from memory without ever reaching the model.
    identity = await _personalize(
        session, user_id=user_id, message=message, identity=identity
    )

    # Fast path: a direct question about a fact Gummy already stores is answered
    # from memory with no model call. Placed BEFORE embedding because embedding
    # is itself part of the latency being avoided — checking after it would save
    # only the generation half. Declines cheaply and falls through.
    instant = await _try_instant_recall(session, user_id=user_id, message=message)
    if instant is not None:
        async for event in _finish_instant_turn(
            session,
            conversation=conversation,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
            answer=instant,
            turn_start=turn_start,
            is_first_turn=is_first_turn,
            llm=llm,
        ):
            yield event
        return

    # Build the grounded prompt (same pipeline as generate_grounded_reply).
    # Embedding is timed separately from candidate retrieval/ranking by
    # pre-embedding the query and handing the vector to the retriever.
    embed_start = time.perf_counter()
    query_vector = await embedding_service.embed_query(message)
    embedding_ms = _ms(embed_start)

    # Multi-Agent Workforce (M8): pick the agent that answers *before* building
    # knowledge, so M8.5 can gate live web search on the selected specialist.
    # Deterministic + free (the keyword router runs without an LLM by default);
    # ``None`` selected_agent on the legacy path leaves the prompt unchanged.
    selected_agent, assistant_metadata, persona = await _select_stream_agent(
        message=message,
        agent_context=conversation.agent_context,
        agent_key=agent_key,
        knowledge_block="",
        llm=llm,
    )

    retrieve_start = time.perf_counter()
    knowledge, web_sources = await _build_knowledge(
        session,
        user_id=user_id,
        message=message,
        embedding_service=embedding_service,
        attachment_file_ids=attachment_file_ids,
        query_vector=query_vector,
        agent_key=selected_agent,
    )
    retrieve_memories_ms = _ms(retrieve_start)

    prompt_start = time.perf_counter()
    # Continuity: when the user refers back to a past discussion, fold in the
    # most relevant *other* conversations (best-effort; never blocks the reply).
    prior_context = await conversation_continuity_service.gather_prior_context(
        session,
        user_id=user_id,
        message=message,
        embedding_service=embedding_service,
        current_conversation_id=conversation_id,
    )
    payload = prompt_builder.build_prompt(
        context=_EMPTY_CONTEXT,
        query=message,
        history=history,
        summary=summary_text,
        identity=identity,
        prior_context=prior_context,
        knowledge=knowledge.block,
    )
    # B11: carry the live web sources on the persisted metadata so the client can
    # render the 🌐 Web Sources disclosure from the refetched message too.
    if web_sources and assistant_metadata is not None:
        assistant_metadata = {**assistant_metadata, "web_sources": web_sources}
    system = f"{persona}\n\n{payload.system}" if persona else payload.system
    if selected_agent is not None:
        _emit_stream_route_analytics(
            user_id=user_id,
            selected_agent=selected_agent,
            overridden=agent_key is not None,
        )
    prompt_build_ms = _ms(prompt_start)

    # Stream the reply, accumulating the full text for persistence. Record the
    # latency to the FIRST emitted token — the metric that drives perceived speed.
    chunks: list[str] = []
    llm_start = time.perf_counter()
    first_token_ms: float | None = None
    if isinstance(llm, SupportsStreaming):
        async for chunk in llm.stream(system=system, messages=payload.messages):
            if first_token_ms is None:
                first_token_ms = _ms(llm_start)
            chunks.append(chunk)
            yield {"type": "delta", "text": chunk}
        model = getattr(llm, "_default_model", llm.name)
    else:
        response = await llm.generate(system=system, messages=payload.messages)
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
        memories_used=knowledge.memories_used,
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
        input_tokens=estimate_tokens(system),
        output_tokens=estimate_tokens(reply_text),
        extra_metadata=assistant_metadata,
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

    # Goal Intelligence (M5.5): a goal-like statement in the user's message is
    # surfaced as a candidate for the client to render a "Goal Detected" prompt.
    # It is never auto-created — confirmation is an explicit user action.
    goal_candidate = _detect_goal_candidate(message)

    yield {
        "type": "done",
        "conversation_id": str(conversation_id),
        "user_message_id": str(user_message.id),
        "assistant_message_id": str(assistant_message.id),
        "model": model,
        "memories_used": knowledge.memories_used,
        # Short contents of the grounding memories so the client can show a
        # "Memory Used" disclosure (never the embeddings/scores — just the fact).
        "memories": [
            i.content
            for i in knowledge.items
            if i.source == knowledge_retrieval_service.SOURCE_MEMORY
        ],
        "message_count": message_count,
        # M8: the agent that answered (Auto-routed or manually overridden), so
        # the client badges the reply with the real backend decision. ``None``
        # on the legacy path (orchestration disabled).
        "agent": selected_agent,
        # M8.5: live web sources used to ground this reply (B11), or [].
        "web_sources": web_sources,
        "goal_candidate": (
            goal_candidate.model_dump(mode="json") if goal_candidate else None
        ),
    }
