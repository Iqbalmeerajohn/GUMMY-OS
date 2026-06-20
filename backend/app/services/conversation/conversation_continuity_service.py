"""Conversation continuity — pull context from *past* conversations.

When the user refers back to an earlier discussion ("continue our previous
chat", "what did we discuss yesterday?", "the startup idea from last week"),
durable facts in long-term memory aren't enough — they want the thread of a
specific prior conversation. This service detects that intent and surfaces the
most relevant *other* conversations (by title + rolling summary), which the turn
service injects into the prompt as a ``<prior_conversations>`` block.

Read-only and best-effort: any failure returns ``None`` so a continuity miss
never costs the user their reply.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ConversationSearchMode, SummaryType
from app.repositories import conversation_summary_repository as sum_repo
from app.services.conversation import conversation_search_service
from app.services.embeddings.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

# Phrasings that signal the user is referring to an earlier conversation. Kept
# deliberately broad — a false positive only adds a cheap search whose results
# are ignored by the model when irrelevant.
_CONTINUITY_MARKERS: tuple[str, ...] = (
    "continue our",
    "continue the",
    "continue where",
    "previous conversation",
    "previous discussion",
    "previous chat",
    "last conversation",
    "last discussion",
    "last time",
    "earlier conversation",
    "earlier you",
    "we discussed",
    "we talked about",
    "we were discussing",
    "you mentioned",
    "as i mentioned",
    "yesterday",
    "last week",
    "last month",
    "the other day",
    "remember when",
    "remember our",
    "from last",
    "pick up where",
    "going back to",
)

# How many prior conversations to fold into the prompt.
_MAX_PRIOR_CONVERSATIONS = 3


def references_past_conversation(message: str) -> bool:
    """True when the message refers back to an earlier conversation."""
    lowered = message.lower()
    return any(marker in lowered for marker in _CONTINUITY_MARKERS)


async def gather_prior_context(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    message: str,
    embedding_service: EmbeddingService,
    current_conversation_id: uuid.UUID | None = None,
    limit: int = _MAX_PRIOR_CONVERSATIONS,
) -> str | None:
    """Render relevant *other* conversations when the user refers to the past.

    Returns ``None`` when the message isn't continuity-flavored, when nothing
    relevant is found, or on any error (best-effort). Otherwise a short block of
    ``- "Title": summary`` lines for the prompt.
    """
    if not references_past_conversation(message):
        return None

    try:
        hits = await conversation_search_service.search(
            session,
            user_id=user_id,
            query=message,
            mode=ConversationSearchMode.HYBRID,
            limit=limit + 1,  # +1 headroom to drop the current thread
            embedding_service=embedding_service,
        )
    except Exception:
        logger.warning("continuity search failed; skipping prior context")
        return None

    lines: list[str] = []
    for hit in hits:
        conversation = hit.conversation
        if (
            current_conversation_id is not None
            and conversation.id == current_conversation_id
        ):
            continue

        rolling = await sum_repo.latest_summary(
            session,
            conversation_id=conversation.id,
            user_id=user_id,
            summary_type=SummaryType.ROLLING,
        )
        title = conversation.title or "Untitled conversation"
        if rolling is not None and rolling.content.strip():
            lines.append(f'- "{title}": {rolling.content.strip()}')
        else:
            lines.append(f'- "{title}"')

        if len(lines) >= limit:
            break

    return "\n".join(lines) if lines else None
