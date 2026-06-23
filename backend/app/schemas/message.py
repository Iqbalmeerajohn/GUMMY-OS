"""Pydantic schemas for messages (read/history wire contract).

M3 exposes message *history* only (read). Appending messages is part of the turn
endpoint (M4), so there is no MessageCreate here yet.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import MessageRole
from app.schemas.goal import GoalCandidate


class MessageResponse(BaseModel):
    """A message turn as returned by the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    seq: int
    role: MessageRole
    content: str
    token_count: int | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    # ORM attribute is ``extra_metadata`` (the column is ``metadata``); expose it
    # to clients as ``metadata``.
    metadata: dict | None = Field(default=None, validation_alias="extra_metadata")
    created_at: datetime


class MessageListResponse(BaseModel):
    """A paginated list of a conversation's messages (oldest first)."""

    items: list[MessageResponse]
    total: int
    limit: int
    offset: int


class TurnRequest(BaseModel):
    """A user message that drives one conversation turn."""

    message: str = Field(min_length=1, max_length=4000)
    # File Intelligence (M6.5): ids of previously-uploaded files attached to
    # this message. When present, file grounding uses ONLY these files (not a
    # broad search). Each must belong to the tenant (foreign id → 404).
    attachment_file_ids: list[uuid.UUID] | None = Field(default=None, max_length=10)

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be empty or whitespace")
        return stripped


class TurnResponse(BaseModel):
    """The result of a persisted turn: the assistant reply + persistence info."""

    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    reply: str
    model: str
    memories_used: int
    input_tokens: int
    output_tokens: int
    message_count: int
    # A goal-like statement detected in the user's message (M5.5), offered for
    # explicit confirmation. ``None`` when the message isn't goal-shaped.
    goal_candidate: GoalCandidate | None = None
