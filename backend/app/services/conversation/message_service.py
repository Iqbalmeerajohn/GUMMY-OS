"""Message service — read/history business logic for a conversation's turns.

M3 scope: serve message *history*, ownership-checked. Appending messages and
orchestrating a turn (retrieval, LLM, persistence) belong to the turn service in
M4 — deliberately not here, to keep responsibilities narrow (PHASE2_PLAN.md §11).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.repositories import message_repository as repo
from app.services.conversation import conversation_service


async def list_messages(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    limit: int,
    offset: int,
) -> tuple[list[Message], int]:
    """Return a page of a conversation's messages (oldest first) + total.

    Resolves the conversation first (404 if it is not the tenant's) so history
    requests for unknown/foreign threads fail cleanly rather than returning an
    empty page.
    """
    # Ownership / existence check (raises 404 if not the tenant's).
    await conversation_service.get_conversation(
        session, user_id=user_id, conversation_id=conversation_id
    )
    return await repo.list_messages(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
