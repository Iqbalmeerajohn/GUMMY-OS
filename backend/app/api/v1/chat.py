"""Memory-aware chat endpoint (``/api/v1/chat``).

Thin HTTP layer: resolve the tenant, session, embedding + LLM providers, delegate
to the chat service, and shape the response.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import (
    CurrentUserId,
    DbSession,
    EmbeddingServiceDep,
    LLMProviderDep,
    SettingsDep,
)
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.memory import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse, summary="Memory-aware chat")
async def chat(
    payload: ChatRequest,
    user_id: CurrentUserId,
    db: DbSession,
    embeddings: EmbeddingServiceDep,
    llm: LLMProviderDep,
    settings: SettingsDep,
) -> ChatResponse:
    result = await chat_service.chat(
        db,
        user_id=user_id,
        message=payload.message,
        embedding_service=embeddings,
        llm=llm,
        token_budget=settings.context_token_budget,
        max_memories=settings.context_max_memories,
    )
    return ChatResponse(
        reply=result.reply,
        model=result.model,
        memories_used=result.memories_used,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
