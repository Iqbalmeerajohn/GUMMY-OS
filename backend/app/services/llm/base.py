"""LLM provider interface.

A provider turns a system prompt + chat messages into a completion. Implementations
(Claude today; OpenAI/Gemini later) are swappable behind this Protocol so the chat
service never depends on a concrete SDK.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LLMResponse:
    """A normalized completion result, independent of the backend provider."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str


@runtime_checkable
class LLMProvider(Protocol):
    """Generates a completion from a system prompt and chat messages."""

    @property
    def name(self) -> str:
        """Provider identifier (e.g. ``claude``)."""
        ...

    async def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Produce a completion. Implementations map errors to ``AppError``."""
        ...


@runtime_checkable
class SupportsStreaming(Protocol):
    """A provider that can stream a completion as incremental text deltas.

    Optional capability: providers implement this when token-by-token output is
    available (Ollama today). Callers detect support with ``isinstance(llm,
    SupportsStreaming)`` and fall back to ``generate`` otherwise.
    """

    def stream(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield reply text deltas in order. Maps errors to ``AppError``."""
        ...
