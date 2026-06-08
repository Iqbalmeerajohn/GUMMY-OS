"""Pydantic schemas for messages (read/history wire contract).

M3 exposes message *history* only (read). Appending messages is part of the turn
endpoint (M4), so there is no MessageCreate here yet.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MessageRole


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
