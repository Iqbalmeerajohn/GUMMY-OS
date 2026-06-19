"""Conversation service — lifecycle business logic for chat threads.

Owns thread lifecycle (create / get / list / rename·pin·archive / soft-delete),
404 semantics, and the transaction boundary (commits its unit of work). It does
**not** orchestrate turns, summaries, extraction, retrieval, or search — those are
later milestones. Narrow by design (see PHASE2_PLAN.md §11).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import CONVERSATION_TITLE_MAX_LENGTH
from app.core.exceptions import AppError
from app.models.conversation import Conversation
from app.models.enums import AgentContext, ConversationStatus, MessageRole
from app.repositories import conversation_repository as repo
from app.repositories import message_repository as msg_repo
from app.schemas.conversation import ConversationCreate, ConversationUpdate
from app.services.llm.base import LLMProvider

_TITLE_SYSTEM = (
    "You generate a short, specific title for a chat conversation. Reply with "
    "ONLY the title: 3-6 words, no surrounding quotes, no trailing punctuation."
)


class ConversationNotFoundError(AppError):
    """Raised when a conversation does not exist (or is soft-deleted) here."""

    def __init__(self, conversation_id: uuid.UUID) -> None:
        super().__init__(
            f"Conversation {conversation_id} not found.",
            code="conversation_not_found",
            status_code=404,
        )


class EmptyUpdateError(AppError):
    """Raised when an update request carries no changeable fields."""

    def __init__(self) -> None:
        super().__init__(
            "No fields provided to update.",
            code="empty_update",
            status_code=400,
        )


async def create_conversation(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    payload: ConversationCreate,
) -> Conversation:
    """Create an empty conversation thread."""
    conversation = await repo.create_conversation(
        session,
        user_id=user_id,
        title=payload.title,
        agent_context=payload.agent_context,
    )
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def get_conversation(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> Conversation:
    """Return a tenant-scoped, non-deleted conversation or raise 404."""
    conversation = await repo.get_conversation(
        session, conversation_id=conversation_id, user_id=user_id
    )
    if conversation is None:
        raise ConversationNotFoundError(conversation_id)
    return conversation


async def list_conversations(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    status: ConversationStatus | None,
    agent_context: AgentContext | None,
    pinned: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[Conversation], int]:
    """Return a page of conversations and the total match count."""
    return await repo.list_conversations(
        session,
        user_id=user_id,
        status=status,
        agent_context=agent_context,
        pinned=pinned,
        limit=limit,
        offset=offset,
    )


async def update_conversation(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
) -> Conversation:
    """Rename / pin / archive / re-tag a conversation."""
    conversation = await get_conversation(
        session, user_id=user_id, conversation_id=conversation_id
    )

    # Only the fields the client actually sent (so e.g. pinned=False is honored,
    # but omitted fields are left untouched).
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise EmptyUpdateError()

    await repo.update_conversation(
        session,
        conversation,
        title=changes.get("title"),
        pinned=changes.get("pinned"),
        status=changes.get("status"),
        agent_context=changes.get("agent_context"),
    )
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def delete_conversation(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> None:
    """Soft-delete a conversation. Raises 404 if not found."""
    conversation = await get_conversation(
        session, user_id=user_id, conversation_id=conversation_id
    )
    await repo.soft_delete_conversation(
        session, conversation, deleted_at=datetime.now(UTC)
    )
    await session.commit()


async def backfill_title(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    llm: LLMProvider,
) -> str | None:
    """Generate and set a title from the first exchange (enrichment consumer).

    Idempotent and best-effort: a no-op (returns ``None``) when the conversation
    is gone, already titled, or has no user message yet. Flushes but does NOT
    commit — the enrichment worker owns the unit of work.
    """
    conversation = await repo.get_conversation(
        session, conversation_id=conversation_id, user_id=user_id
    )
    if conversation is None or conversation.title is not None:
        return None

    # Title from the first user message (the topic of the thread).
    messages, _ = await msg_repo.list_messages(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        limit=4,
        offset=0,
    )
    basis = next(
        (m.content for m in messages if m.role is MessageRole.USER), None
    )
    if basis is None:
        return None

    try:
        response = await llm.generate(
            system=_TITLE_SYSTEM,
            messages=[{"role": "user", "content": basis}],
        )
        title = response.text.strip().strip('"').strip()
    except Exception:
        # LLM unavailable → still title the thread (never leave it "Untitled").
        title = ""

    # Fallback: a clean snippet of the first user message beats "Untitled".
    if not title:
        title = _fallback_title(basis)
    if not title:
        return None
    title = title[:CONVERSATION_TITLE_MAX_LENGTH]

    await repo.update_conversation(session, conversation, title=title)
    return title


def _fallback_title(first_message: str) -> str:
    """Deterministic title from the first user message (no LLM).

    Takes the leading words, trims trailing punctuation, and caps the length —
    e.g. "where do i live?" → "Where do i live". Empty only if there are no
    word characters at all.
    """
    words = first_message.strip().split()
    snippet = " ".join(words[:8]).rstrip(" .,!?;:").strip()
    if not snippet:
        return ""
    return snippet[0].upper() + snippet[1:]
