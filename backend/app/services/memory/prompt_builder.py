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


def _render_goals(goals: list[dict[str, object]]) -> str:
    """Render active goals as compact, one-per-line context for the prompt."""
    lines: list[str] = []
    for goal in goals:
        parts = [f"priority: {goal.get('priority', 'medium')}"]
        target = goal.get("target_date")
        if target:
            parts.append(f"target: {target}")
        parts.append(f"progress: {goal.get('progress_percentage', 0)}%")
        lines.append(f"- {goal.get('title', '')} ({', '.join(parts)})")
    return "\n".join(lines)


def _render_files(files: dict[str, object]) -> str:
    """Render the file grounding block (inventory + retrieved excerpts).

    ``files`` carries an ``inventory`` (list of file metadata, so the assistant
    can answer "what files do I have?") and ``excerpts`` (retrieved chunk
    content with its source filename, so it can answer *from* the documents).
    """
    sections: list[str] = []
    inventory = files.get("inventory") or []
    if isinstance(inventory, list) and inventory:
        lines = []
        for f in inventory:
            if not isinstance(f, dict):
                continue
            lines.append(
                f"- {f.get('filename', '')} "
                f"({f.get('processing_status', 'unknown')}, "
                f"{f.get('chunk_count', 0)} chunks, "
                f"uploaded {f.get('uploaded_at', 'n/a')})"
            )
        if lines:
            sections.append("Uploaded files:\n" + "\n".join(lines))
    excerpts = files.get("excerpts") or []
    if isinstance(excerpts, list) and excerpts:
        lines = []
        for e in excerpts:
            if not isinstance(e, dict):
                continue
            lines.append(f"[{e.get('filename', 'file')}] {e.get('content', '')}")
        if lines:
            sections.append("Relevant content from the files:\n" + "\n\n".join(lines))
    return "\n\n".join(sections)


_KNOWLEDGE_GUIDANCE = (
    "The unified knowledge below is retrieved from everything the user has told "
    "you — their memories, goals, and uploaded files — each item tagged with its "
    "source. Answer using it when relevant (cite a filename when you use file "
    "content); if the answer is not here, say you don't have that information yet "
    "rather than guessing. When a file is attached, prefer it.\n"
    "Use this context silently. Draw on it only when it genuinely helps answer "
    "what was asked, and let it shape the answer rather than becoming the "
    "subject of one. Do not recite it, do not list what you know about the user, "
    "and do not announce that you remembered something — no 'as you told me "
    "before', 'I recall that', or 'based on your memories'. If none of it bears "
    "on the request, ignore it entirely and answer normally."
)


def build_prompt(
    *,
    context: ContextPackage,
    query: str,
    history: list[dict[str, str]] | None = None,
    summary: str | None = None,
    identity: str | None = None,
    prior_context: str | None = None,
    goals: list[dict[str, object]] | None = None,
    files: dict[str, object] | None = None,
    knowledge: str | None = None,
) -> PromptPayload:
    """Build the system prompt + chat messages for a grounded turn.

    ``history`` is the recent prior turns of THIS conversation (working memory),
    each a ``{"role", "content"}`` dict, prepended before the current ``query``.
    ``summary`` is the thread's rolling summary (compressed older context).
    ``identity`` is the authenticated user-profile block (see the identity
    service); it precedes the grounding so every agent knows who the user is.
    ``prior_context`` is relevant context pulled from *other* conversations when
    the user references a past discussion (conversation continuity).

    Grounding has two mutually-exclusive shapes:

    * **unified** (M7) — when ``knowledge`` (a rendered ``<knowledge>`` body from
      the Unified Knowledge Engine) is supplied, it replaces the separate
      ``<memory>``/``<goals>``/``<files>`` blocks with one attributed block;
    * **legacy** — otherwise ``context`` (memories), ``goals``, and ``files`` are
      rendered as independent blocks. All default to ``None`` so the legacy path
      stays byte-identical for the existing callers and tests.
    """
    identity_block = f"{identity}\n\n" if identity else ""

    if knowledge is not None and knowledge.strip():
        system = (
            f"{_PERSONA}\n\n"
            f"{identity_block}"
            f"{_KNOWLEDGE_GUIDANCE}\n\n"
            f"=== KNOWLEDGE ===\n"
            f"<knowledge>\n{knowledge}\n</knowledge>"
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

    system = (
        f"{_PERSONA}\n\n"
        f"{identity_block}"
        f"{_GROUNDING}\n\n"
        f"Remembered context about the user:\n"
        f"<memory>\n{_render_context(context)}\n</memory>"
    )
    if goals:
        system += (
            "\n\nThe user's active goals. Reference them naturally ONLY when "
            "relevant to the user's request (e.g. when planning, prioritizing, "
            "or deciding what to do); do not bring them up otherwise:\n"
            f"<goals>\n{_render_goals(goals)}\n</goals>"
        )
    if files:
        rendered_files = _render_files(files)
        if rendered_files:
            system += (
                "\n\nThe user's uploaded files. When the user asks about their "
                "documents (or a file is attached), answer using the content "
                "below and cite the filename; if it isn't there, say so rather "
                "than guessing:\n"
                f"<files>\n{rendered_files}\n</files>"
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
