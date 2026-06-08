"""Conversation endpoints (``/api/v1/conversations``).

Thin HTTP layer: resolve the tenant + session, delegate to the conversation /
message services, and shape the response. No business logic here. M3 covers
lifecycle CRUD + message history; the turn endpoint arrives in M4.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import (
    CurrentUserId,
    DbSession,
    EmbeddingServiceDep,
    LLMProviderDep,
    SettingsDep,
)
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.models.enums import AgentContext, ConversationStatus
from app.schemas.conversation import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
)
from app.schemas.message import (
    MessageListResponse,
    MessageResponse,
    TurnRequest,
    TurnResponse,
)
from app.services.conversation import (
    conversation_service,
    conversation_turn_service,
    message_service,
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
    user_id: CurrentUserId,
    db: DbSession,
    embeddings: EmbeddingServiceDep,
    llm: LLMProviderDep,
    settings: SettingsDep,
) -> TurnResponse:
    result = await conversation_turn_service.run_turn(
        db,
        user_id=user_id,
        conversation_id=conversation_id,
        message=payload.message,
        embedding_service=embeddings,
        llm=llm,
        token_budget=settings.context_token_budget,
        max_memories=settings.context_max_memories,
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
    )
