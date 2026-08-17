"""Conversation→memory extraction (Phase 2, M6).

Distils durable facts from a conversation's new messages and persists them as
long-term memories — **exclusively through the existing Memory Engine**
(``memory_service.create_memory``), so scoring, versioning, and embedding are not
reimplemented here. Each created memory gets a ``memory_sources`` provenance link.

Consent-gated (memory-system §2): only ``autonomous`` mode auto-saves; ``explicit``
and ``assisted`` persist nothing automatically (the assisted proposal surface is
future work). A per-conversation watermark (``last_extracted_seq``) prevents
re-extracting — and thus re-saving — the same facts.

Flush-only for the watermark; ``memory_service`` owns the memory commit and the
enrichment worker owns the unit of work.
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import (
    EXTRACTION_MAX_MEMORIES,
    SUMMARY_MAX_DELTA_MESSAGES,
)
from app.models.enums import ConsentMode, MemoryCategory, SourceKind
from app.models.memory import Memory
from app.repositories import conversation_repository as conv_repo
from app.repositories import memory_source_repository as src_repo
from app.repositories import message_repository as msg_repo
from app.schemas.memory import MemoryCreate
from app.services.llm.base import LLMProvider, SupportsJsonMode
from app.services.memory import memory_service, timeline, user_profile_service

logger = logging.getLogger(__name__)

# Categories that must NEVER be auto-saved (memory-system §2). None of the current
# MemoryCategory values are sensitive; this guard is wired for when health/finance/
# credential categories are introduced.
_SENSITIVE_CATEGORIES: frozenset[MemoryCategory] = frozenset()

_CATEGORY_VALUES = ", ".join(c.value for c in MemoryCategory)
_EXTRACTION_SYSTEM = (
    "You maintain a long-term memory about the USER. From the conversation "
    "excerpt, extract durable facts worth remembering across future "
    "conversations. Return ONLY a JSON array; each item is "
    '{"content": "<fact>", "category": "<one of: '
    f'{_CATEGORY_VALUES}>"}}.\n\n'
    "Write each fact as a concise, standalone statement about the user, in the "
    "third person, the way it would read on a profile — NOT as a description of "
    "the conversation.\n"
    '  GOOD: "Lives in Vizag"\n'
    '  GOOD: "Favorite football player is Cristiano Ronaldo"\n'
    '  GOOD: "Building GUMMY, a personal AI operating system"\n'
    '  BAD:  "User is asking about Vizag"  (a one-time question)\n'
    '  BAD:  "User wants information"  (generic assistant observation)\n'
    '  BAD:  "The user said hello"  (small talk / transient)\n\n'
    "ONLY store: personal facts (profile), preferences, goals, projects, "
    "career information, skills being learned, and recurring interests.\n"
    "NEVER store: one-time questions, requests, or tasks; temporary "
    "conversation summaries; generic observations about what the assistant did "
    "or what the user is currently asking. When in doubt, leave it out.\n\n"
    "If there is nothing durable worth saving, return []."
)


def _resolve_consent(consent_mode: ConsentMode | None) -> ConsentMode:
    if consent_mode is not None:
        return consent_mode
    try:
        return ConsentMode(get_settings().memory_consent_mode.lower())
    except ValueError:
        return ConsentMode.ASSISTED  # safe default


# Deterministic backstop for the prompt: phrasings that signal a conversation
# summary / one-time question rather than a durable fact. Dropped even if the
# model returns them.
_LOW_QUALITY_MARKERS: tuple[str, ...] = (
    "user is",
    "user wants",
    "user asked",
    "user is asking",
    "is asking about",
    "is seeking",
    "seeking information",
    "wants to know",
    "is looking for",
    "would like to know",
    "the assistant",
    "the conversation",
)


def _is_low_quality(content: str) -> bool:
    """True for conversation-summary / one-time-question phrasings."""
    lowered = content.lower()
    return any(marker in lowered for marker in _LOW_QUALITY_MARKERS)


# Last-resort recovery for a malformed item. Small models drop a closing quote
# often enough that discarding the whole batch loses real facts — observed from
# qwen2.5:3b: `[{"content": "Iqbal lives in Bangalore", "category": "profile}]`.
# Constrained decoding (SupportsJsonMode) prevents this at the source; this is
# the net for providers that cannot constrain.
_SALVAGE_ITEM = re.compile(
    r'"content"\s*:\s*"(?P<content>(?:[^"\\]|\\.)*)"'
    r'\s*,\s*"category"\s*:\s*"?(?P<category>[a-z_]+)',
    re.IGNORECASE,
)


def _salvage(text: str) -> list[dict[str, str]]:
    """Recover content/category pairs from JSON that failed to parse."""
    items = [
        {"content": m.group("content"), "category": m.group("category")}
        for m in _SALVAGE_ITEM.finditer(text)
    ]
    if items:
        logger.info("extraction: salvaged %d item(s) from malformed JSON", len(items))
    return items


def _parse_candidates(text: str) -> list[tuple[MemoryCategory, str]]:
    """Parse the LLM's JSON array into validated (category, content) pairs."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Strip a ```json ... ``` fence if the model added one.
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    raw: object
    try:
        raw = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        raw = _salvage(cleaned)
        if not raw:
            logger.warning("extraction: could not parse LLM output as JSON")
            return []
    # JSON mode yields an object, not a bare array, when the model wraps the list
    # in a key ({"memories": [...]}) — accept the first list-valued field.
    if isinstance(raw, dict):
        raw = next(
            (v for v in raw.values() if isinstance(v, list)),
            [raw] if "content" in raw else [],
        )
    if not isinstance(raw, list):
        return []

    candidates: list[tuple[MemoryCategory, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        category_raw = str(item.get("category", "")).strip().lower()
        if not content or _is_low_quality(content):
            continue
        try:
            category = MemoryCategory(category_raw)
        except ValueError:
            continue
        if category in _SENSITIVE_CATEGORIES:
            continue
        candidates.append((category, content))
    return candidates


async def extract_and_store(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    llm: LLMProvider,
    consent_mode: ConsentMode | None = None,
) -> list[Memory]:
    """Extract durable facts from the unsummarized delta and store them.

    Returns the memories created (empty when consent forbids, nothing is due, or
    nothing worth saving was found). Routes every memory through
    ``memory_service``; links provenance in ``memory_sources``.
    """
    mode = _resolve_consent(consent_mode)
    if mode is not ConsentMode.AUTONOMOUS:
        # explicit → no automatic extraction; assisted → proposals (future work).
        return []

    conversation = await conv_repo.get_conversation(
        session, conversation_id=conversation_id, user_id=user_id
    )
    if conversation is None:
        return []

    delta = await msg_repo.messages_after(
        session,
        conversation_id=conversation_id,
        user_id=user_id,
        after_seq=conversation.last_extracted_seq,
        limit=SUMMARY_MAX_DELTA_MESSAGES,
    )
    if not delta:
        return []

    # Per-turn extraction: process any new messages immediately so a single
    # short fact ("My favorite player is …") is captured without waiting for
    # the thread to accumulate. The extraction prompt returns [] when there is
    # nothing worth saving, so trivial turns cost one cheap call and persist
    # nothing.

    # Advance the watermark first (on the still-fresh instance). memory_service
    # commits below, persisting this too; on an LLM failure the whole unit of work
    # rolls back, so the window is retried rather than silently skipped.
    target_seq = delta[-1].seq
    await conv_repo.set_extraction_watermark(session, conversation, seq=target_seq)

    transcript = "\n".join(f"{m.role.value}: {m.content}" for m in delta)
    # Constrained decoding when the provider supports it. Free-form prompting for
    # JSON is not reliable on a 3B local model, and an unparseable response
    # silently discards every fact in the window — the failure that makes the
    # product's central promise stop working with no visible error.
    if isinstance(llm, SupportsJsonMode):
        response = await llm.generate_json(
            system=_EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": transcript}],
        )
    else:
        response = await llm.generate(
            system=_EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": transcript}],
        )
    candidates = _parse_candidates(response.text)[:EXTRACTION_MAX_MEMORIES]

    created: list[Memory] = []
    for category, content in candidates:
        # Reuse the Memory Engine: scoring defaults, versioning, embedding sync.
        memory = await memory_service.create_memory(
            session,
            user_id=user_id,
            payload=MemoryCreate(category=category, content=content),
        )
        # Anchor events in time when the fact says when it happened. Only set
        # it once: a reinforced existing memory keeps its original date, since
        # restating something does not move when it occurred.
        if memory.occurred_at is None:
            memory.occurred_at = timeline.parse_occurred_at(content)
        await src_repo.link_source(
            session,
            user_id=user_id,
            memory_id=memory.id,
            conversation_id=conversation_id,
            source_kind=SourceKind.CONVERSATION,
        )
        created.append(memory)

    if created:
        # New facts may change who GUMMY thinks this person is. Re-derived here,
        # off the turn's critical path, so the hot path never pays for it.
        await user_profile_service.refresh_traits(session, user_id=user_id)
    return created
