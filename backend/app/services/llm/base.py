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


@dataclass(frozen=True)
class ToolCall:
    """One tool the model asked to run, normalized across providers."""

    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ToolCallResponse:
    """A model turn that may be a final answer, tool calls, or both."""

    text: str
    tool_calls: list[ToolCall]
    model: str
    input_tokens: int
    output_tokens: int
    stop_reason: str

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


@runtime_checkable
class SupportsToolCalling(Protocol):
    """A provider that can be offered tools and may ask to call them.

    Optional capability, detected with ``isinstance(llm, SupportsToolCalling)``.
    A provider without it simply never gets tools, and the agent answers from
    context alone — the tool loop degrades to the previous behaviour rather than
    failing, so selecting a model that cannot call tools is a limitation and not
    an outage.
    """

    async def generate_with_tools(
        self,
        *,
        system: str,
        messages: list[dict],
        tools: list[dict],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> ToolCallResponse:
        """Generate, offering ``tools`` (JSON Schema function definitions)."""
        ...


@runtime_checkable
class SupportsJsonMode(Protocol):
    """A provider that can constrain its output to syntactically valid JSON.

    Optional capability, detected with ``isinstance(llm, SupportsJsonMode)``.

    This exists because asking a small local model for JSON in the prompt is not
    enough. Observed from ``qwen2.5:3b`` on the memory-extraction prompt:

        [{"content": "Iqbal lives in Bangalore", "category": "profile}]

    — a missing closing quote, which fails ``json.loads`` and silently discards
    the fact. Constrained decoding makes that class of error impossible at the
    source rather than repairing it afterwards.
    """

    async def generate_json(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Produce a completion guaranteed to parse as JSON."""
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
