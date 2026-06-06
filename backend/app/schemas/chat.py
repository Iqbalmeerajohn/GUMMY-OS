"""Schemas for the memory-aware chat endpoint."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    """A single chat message from the user."""

    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def _strip_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("message must not be empty or whitespace")
        return stripped


class ChatResponse(BaseModel):
    """The assistant's reply plus lightweight metadata."""

    reply: str
    model: str
    memories_used: int
    input_tokens: int
    output_tokens: int
