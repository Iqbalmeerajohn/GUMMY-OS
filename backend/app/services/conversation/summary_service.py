"""Summary service — rolling conversation summaries + their embeddings (M5).

Maintains a versioned rolling summary per thread so long conversations stay cheap
to contextualize. Trigger policy (PHASE2_PLAN.md §21 Q2): token-pressure primary,
with a message-count safety cap — a refresh fires when the unsummarized delta
exceeds EITHER threshold.

Flushes through the repositories but does NOT commit — the enrichment worker owns
the unit of work. No extraction or search here.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    SUMMARY_MAX_DELTA_MESSAGES,
    SUMMARY_TRIGGER_MESSAGE_COUNT,
    SUMMARY_TRIGGER_TOKEN_THRESHOLD,
)
from app.models.conversation_summary import ConversationSummary
from app.models.enums import SummaryType
from app.models.message import Message
from app.repositories import conversation_summary_embedding_repository as emb_repo
from app.repositories import conversation_summary_repository as sum_repo
from app.repositories import message_repository as msg_repo
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.llm.base import LLMProvider
from app.utils.tokens import estimate_tokens

_SUMMARY_SYSTEM = (
    "You maintain a running summary of a conversation. Given the previous summary "
    "(if any) and the new messages, produce an updated, concise summary that "
    "captures durable facts, decisions, goals, and open threads. Reply with ONLY "
    "the summary prose — no preamble, no bullet headers."
)


def _render_delta(messages: list[Message]) -> str:
    return "\n".join(f"{m.role.value}: {m.content}" for m in messages)


async def _watermark_seq(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    previous: ConversationSummary | None,
) -> int:
    """The seq the previous summary covered through (0 if none / message gone)."""
    if previous is None or previous.covers_through_message_id is None:
        return 0
    watermark = await msg_repo.get_message(
        session, message_id=previous.covers_through_message_id, user_id=user_id
    )
    return watermark.seq if watermark is not None else 0


async def maybe_refresh_rolling_summary(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    llm: LLMProvider,
    embedding_service: EmbeddingService,
    trigger_token_threshold: int = SUMMARY_TRIGGER_TOKEN_THRESHOLD,
    trigger_message_count: int = SUMMARY_TRIGGER_MESSAGE_COUNT,
) -> ConversationSummary | None:
    """Refresh the rolling summary if the unsummarized delta crosses a threshold.

    Returns the new summary, or ``None`` when nothing was due. Best-effort and
    tenant-scoped; flush-only (the worker commits).
    """
    previous = await sum_repo.latest_summary(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        summary_type=SummaryType.ROLLING,
    )
    after_seq = await _watermark_seq(session, user_id=user_id, previous=previous)
    delta = await msg_repo.messages_after(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        after_seq=after_seq,
        limit=SUMMARY_MAX_DELTA_MESSAGES,
    )
    if not delta:
        return None

    delta_tokens = sum(estimate_tokens(m.content) for m in delta)
    if delta_tokens < trigger_token_threshold and len(delta) < trigger_message_count:
        return None

    # Summarize previous summary + the delta into a fresh rolling summary.
    if previous is not None:
        prompt = (
            f"Previous summary:\n{previous.content}\n\n"
            f"New messages:\n{_render_delta(delta)}"
        )
    else:
        prompt = f"Conversation:\n{_render_delta(delta)}"

    response = await llm.generate(
        system=_SUMMARY_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.text.strip()
    if not content:
        return None

    version = await sum_repo.next_version_number(session, conversation_id)
    summary = await sum_repo.add_summary(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        summary_type=SummaryType.ROLLING,
        content=content,
        version_number=version,
        covers_through_message_id=delta[-1].id,
        model=response.model,
    )

    # Embed the new summary (each version is a new row → always a create).
    vector = await embedding_service.embed_query(content)
    await emb_repo.create_embedding(
        session,
        user_id=user_id,
        summary_id=summary.id,
        embedding_model=embedding_service.model_name,
        embedding_dimension=embedding_service.dimension,
        content_hash=embedding_service.compute_content_hash(content),
        embedding_vector=vector,
    )
    return summary
