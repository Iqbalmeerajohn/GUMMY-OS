"""Pydantic schemas for the Conversation API (the wire contract).

Lifecycle only — create, read, update (rename/pin/archive), list. The turn
endpoint (appending messages + generating a reply) lands in M4.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import CONVERSATION_TITLE_MAX_LENGTH
from app.models.enums import AgentContext, ConversationStatus


def _validate_title(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        raise ValueError("title must not be empty or whitespace")
    return stripped


class ConversationCreate(BaseModel):
    """Payload to create a conversation (an empty thread)."""

    title: str | None = Field(default=None, max_length=CONVERSATION_TITLE_MAX_LENGTH)
    agent_context: AgentContext = AgentContext.GENERAL

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        return _validate_title(value)


class ConversationUpdate(BaseModel):
    """Partial update payload. Only provided fields are changed."""

    title: str | None = Field(default=None, max_length=CONVERSATION_TITLE_MAX_LENGTH)
    pinned: bool | None = None
    status: ConversationStatus | None = None
    agent_context: AgentContext | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        return _validate_title(value)


class ConversationResponse(BaseModel):
    """A conversation as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    status: ConversationStatus
    agent_context: AgentContext
    pinned: bool
    last_message_at: datetime | None
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """A paginated list of conversations."""

    items: list[ConversationResponse]
    total: int
    limit: int
    offset: int
