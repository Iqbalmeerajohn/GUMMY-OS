"""Conversation endpoints (``/api/v1/conversations``).

Thin HTTP layer: resolve the tenant + session, delegate to the conversation /
message services, and shape the response. No business logic here. M3 covers
lifecycle CRUD + message history; the turn endpoint arrives in M4.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    CurrentUserDep,
    CurrentUserId,
    DbSession,
    EmbeddingServiceDep,
    LLMProviderDep,
    SettingsDep,
)
from app.core.constants import (
    DEFAULT_PAGE_SIZE,
    DEFAULT_SEARCH_LIMIT,
    MAX_PAGE_SIZE,
    MAX_SEARCH_LIMIT,
)
from app.core.exceptions import AppError
from app.core.security import CurrentUser
from app.models.enums import (
    AgentContext,
    ConversationSearchMode,
    ConversationStatus,
)
from app.repositories import conversation_search_repository
from app.schemas.conversation import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationSearchResponse,
    ConversationSearchResultItem,
    ConversationUpdate,
)
from app.schemas.message import (
    MessageListResponse,
    MessageResponse,
    TurnRequest,
    TurnResponse,
)
from app.schemas.search import (
    MessageSearchResponse,
    MessageSearchResultItem,
)
from app.services.conversation import (
    conversation_search_service,
    conversation_service,
    conversation_turn_service,
    message_service,
)
from app.services.identity.user_context import (
    UserContext,
    build_identity_block,
)


def _identity_for(user: CurrentUser) -> str | None:
    """Safe profile block injected into the turn (name from the verified JWT)."""
    return build_identity_block(
        UserContext(user_id=user.id, name=user.display_name, email=user.email)
    )


router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a conversation",
)
async def create_conversation(
    payload: ConversationCreate,
    user_id: CurrentUserId,
    db: DbSession,
) -> ConversationResponse:
    conversation = await conversation_service.create_conversation(
        db, user_id=user_id, payload=payload
    )
    return ConversationResponse.model_validate(conversation)


@router.get(
    "",
    response_model=ConversationListResponse,
    summary="List conversations",
)
async def list_conversations(
    user_id: CurrentUserId,
    db: DbSession,
    status: ConversationStatus | None = None,
    agent_context: AgentContext | None = None,
    pinned: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ConversationListResponse:
    items, total = await conversation_service.list_conversations(
        db,
        user_id=user_id,
        status=status,
        agent_context=agent_context,
        pinned=pinned,
        limit=limit,
        offset=offset,
    )
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/search",
    response_model=ConversationSearchResponse,
    summary="Search conversations (keyword / semantic / hybrid)",
)
async def search_conversations(
    user_id: CurrentUserId,
    db: DbSession,
    embeddings: EmbeddingServiceDep,
    q: Annotated[str, Query(min_length=1, max_length=1000)],
    mode: ConversationSearchMode = ConversationSearchMode.HYBRID,
    limit: Annotated[int, Query(ge=1, le=MAX_SEARCH_LIMIT)] = DEFAULT_SEARCH_LIMIT,
) -> ConversationSearchResponse:
    query = q.strip()
    if not query:
        raise AppError(
            "query must not be empty or whitespace",
            code="empty_query",
            status_code=422,
        )
    hits = await conversation_search_service.search(
        db,
        user_id=user_id,
        query=query,
        mode=mode,
        limit=limit,
        embedding_service=embeddings,
    )
    return ConversationSearchResponse(
        query=q,
        mode=mode.value,
        count=len(hits),
        results=[
            ConversationSearchResultItem(
                conversation_id=hit.conversation.id,
                title=hit.conversation.title,
                status=hit.conversation.status,
                last_message_at=hit.conversation.last_message_at,
                message_count=hit.conversation.message_count,
                score=hit.score,
                keyword_score=hit.keyword_score,
                semantic_score=hit.semantic_score,
                match_message_id=hit.match_message_id,
            )
            for hit in hits
        ],
    )


@router.get(
    "/message-search",
    response_model=MessageSearchResponse,
    summary="Full-text search over messages (unified search)",
)
async def search_messages(
    user_id: CurrentUserId,
    db: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=1000)],
    limit: Annotated[int, Query(ge=1, le=MAX_SEARCH_LIMIT)] = DEFAULT_SEARCH_LIMIT,
) -> MessageSearchResponse:
    query = q.strip()
    if not query:
        raise AppError(
            "query must not be empty or whitespace",
            code="empty_query",
            status_code=422,
        )
    rows = await conversation_search_repository.message_search(
        db, user_id=user_id, query=query, limit=limit
    )
    results = [
        MessageSearchResultItem(
            message_id=message_id,
            conversation_id=conversation_id,
            conversation_title=title,
            role=getattr(role, "value", str(role)),
            content=content,
            score=score,
        )
        for message_id, conversation_id, role, content, title, score in rows
    ]
    return MessageSearchResponse(query=q, count=len(results), results=results)


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
    summary="Get a conversation by id",
)
async def get_conversation(
    conversation_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> ConversationResponse:
    conversation = await conversation_service.get_conversation(
        db, user_id=user_id, conversation_id=conversation_id
    )
    return ConversationResponse.model_validate(conversation)


@router.patch(
    "/{conversation_id}",
    response_model=ConversationResponse,
    summary="Update a conversation (rename / pin / archive / re-tag)",
)
async def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    user_id: CurrentUserId,
    db: DbSession,
) -> ConversationResponse:
    conversation = await conversation_service.update_conversation(
        db, user_id=user_id, conversation_id=conversation_id, payload=payload
    )
    return ConversationResponse.model_validate(conversation)


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete a conversation",
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> None:
    await conversation_service.delete_conversation(
        db, user_id=user_id, conversation_id=conversation_id
    )


@router.get(
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
    summary="Get a conversation's message history",
)
async def list_messages(
    conversation_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MessageListResponse:
    items, total = await message_service.list_messages(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
    )
    return MessageListResponse(
        items=[MessageResponse.model_validate(m) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=TurnResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run a turn: post a message and get the assistant reply",
)
async def create_turn(
    conversation_id: uuid.UUID,
    payload: TurnRequest,
    current_user: CurrentUserDep,
    db: DbSession,
    embeddings: EmbeddingServiceDep,
    llm: LLMProviderDep,
    settings: SettingsDep,
) -> TurnResponse:
    result = await conversation_turn_service.run_turn(
        db,
        user_id=current_user.id,
        conversation_id=conversation_id,
        message=payload.message,
        embedding_service=embeddings,
        llm=llm,
        token_budget=settings.context_token_budget,
        max_memories=settings.context_max_memories,
        identity=_identity_for(current_user),
        attachment_file_ids=payload.attachment_file_ids,
    )
    return TurnResponse(
        conversation_id=result.conversation_id,
        user_message_id=result.user_message_id,
        assistant_message_id=result.assistant_message_id,
        reply=result.reply,
        model=result.model,
        memories_used=result.memories_used,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        message_count=result.message_count,
        goal_candidate=result.goal_candidate,
    )


@router.post(
    "/{conversation_id}/messages/stream",
    summary="Run a turn with a streamed (SSE) assistant reply",
)
async def create_turn_stream(
    conversation_id: uuid.UUID,
    payload: TurnRequest,
    current_user: CurrentUserDep,
    db: DbSession,
    embeddings: EmbeddingServiceDep,
    llm: LLMProviderDep,
    settings: SettingsDep,
) -> StreamingResponse:
    """Stream the grounded reply as Server-Sent Events.

    Emits ``data: {"type":"delta","text":...}`` per chunk and a terminal
    ``data: {"type":"done",...}``. The full message (user + assistant) is
    persisted once the stream completes, identical to the non-streaming turn.
    """

    identity = _identity_for(current_user)

    async def _events() -> AsyncIterator[str]:
        async for event in conversation_turn_service.stream_turn(
            db,
            user_id=current_user.id,
            conversation_id=conversation_id,
            message=payload.message,
            embedding_service=embeddings,
            llm=llm,
            token_budget=settings.context_token_budget,
            max_memories=settings.context_max_memories,
            identity=identity,
            attachment_file_ids=payload.attachment_file_ids,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
