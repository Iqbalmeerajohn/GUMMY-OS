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


def build_prompt(
    *,
    context: ContextPackage,
    query: str,
    history: list[dict[str, str]] | None = None,
    summary: str | None = None,
    identity: str | None = None,
    prior_context: str | None = None,
) -> PromptPayload:
    """Build the system prompt + chat messages for a memory-grounded turn.

    ``history`` is the recent prior turns of THIS conversation (working memory),
    each a ``{"role", "content"}`` dict, prepended before the current ``query``.
    ``summary`` is the thread's rolling summary (compressed older context).
    ``identity`` is the authenticated user-profile block (see the identity
    service); it precedes memory so every agent knows who the user is.
    ``prior_context`` is relevant context pulled from *other* conversations when
    the user references a past discussion (conversation continuity). All four
    default to ``None`` so the legacy path stays byte-identical.
    """
    identity_block = f"{identity}\n\n" if identity else ""
    system = (
        f"{_PERSONA}\n\n"
        f"{identity_block}"
        f"{_GROUNDING}\n\n"
        f"Remembered context about the user:\n"
        f"<memory>\n{_render_context(context)}\n</memory>"
    )
    if prior_context:
        system += (
            "\n\nRelevant context from the user's earlier conversations "
            "(use it when they refer back to a past discussion):\n"
            f"<prior_conversations>\n{prior_context}\n</prior_conversations>"
        )
    if summary:
        system += (
            "\n\nSummary of earlier in this conversation:\n"
            f"<conversation_summary>\n{summary}\n</conversation_summary>"
        )
    messages = [*(history or []), {"role": "user", "content": query}]
    return PromptPayload(system=system, messages=messages)
