"""Prompt builder — assemble system prompt + memory context + user query.

Produces a provider-agnostic ``PromptPayload`` (a system string and a list of
chat messages) that the LLM gateway can send to any backend. Pure and I/O-free.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.memory.context_assembly_service import (
    ContextPackage,
    render_memory_line,
)

_PERSONA = (
    "You are Gummy, the user's personal AI assistant. You help the user using "
    "what you remember about them. Be warm, concise, and direct."
)

_GROUNDING = (
    "Answer using the remembered context below when it is relevant. If the "
    "context does not contain the answer, say you don't have that information "
    "yet rather than guessing. Respond directly with your final answer — do not "
    "include exploratory reasoning or meta-commentary."
)

_NO_MEMORIES = "(No relevant memories were found for this query.)"


@dataclass(frozen=True)
class PromptPayload:
    """A provider-agnostic prompt: a system prompt and chat messages."""

    system: str
    messages: list[dict[str, str]]


def _render_context(package: ContextPackage) -> str:
    if not package.memories:
        return _NO_MEMORIES
    return "\n".join(render_memory_line(m) for m in package.memories)


def build_prompt(*, context: ContextPackage, query: str) -> PromptPayload:
    """Build the system prompt + user message for a memory-grounded chat turn."""
    system = (
        f"{_PERSONA}\n\n"
        f"{_GROUNDING}\n\n"
        f"Remembered context about the user:\n"
        f"<memory>\n{_render_context(context)}\n</memory>"
    )
    messages = [{"role": "user", "content": query}]
    return PromptPayload(system=system, messages=messages)
