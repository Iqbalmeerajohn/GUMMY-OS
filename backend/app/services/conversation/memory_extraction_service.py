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
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import (
    EXTRACTION_MAX_MEMORIES,
    SUMMARY_MAX_DELTA_MESSAGES,
    SUMMARY_TRIGGER_MESSAGE_COUNT,
    SUMMARY_TRIGGER_TOKEN_THRESHOLD,
)
from app.models.enums import ConsentMode, MemoryCategory, SourceKind
from app.models.memory import Memory
from app.repositories import conversation_repository as conv_repo
from app.repositories import memory_source_repository as src_repo
from app.repositories import message_repository as msg_repo
from app.schemas.memory import MemoryCreate
from app.services.llm.base import LLMProvider
from app.services.memory import memory_service
from app.utils.tokens import estimate_tokens

logger = logging.getLogger(__name__)

# Categories that must NEVER be auto-saved (memory-system §2). None of the current
# MemoryCategory values are sensitive; this guard is wired for when health/finance/
# credential categories are introduced.
_SENSITIVE_CATEGORIES: frozenset[MemoryCategory] = frozenset()

_CATEGORY_VALUES = ", ".join(c.value for c in MemoryCategory)
_EXTRACTION_SYSTEM = (
    "You extract durable, long-term facts about the USER from a conversation "
    "excerpt. Return ONLY a JSON array; each item is "
    '{"content": "<concise fact>", "category": "<one of: '
    f"{_CATEGORY_VALUES}>\"}}. "
    "Include only stable facts worth remembering (identity, goals, preferences, "
    "projects, skills) — not small talk or transient details. If there is nothing "
    "worth saving, return []."
)


def _resolve_consent(consent_mode: ConsentMode | None) -> ConsentMode:
    if consent_mode is not None:
        return consent_mode
    try:
        return ConsentMode(get_settings().memory_consent_mode.lower())
    except ValueError:
        return ConsentMode.ASSISTED  # safe default


def _parse_candidates(text: str) -> list[tuple[MemoryCategory, str]]:
    """Parse the LLM's JSON array into validated (category, content) pairs."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Strip a ```json ... ``` fence if the model added one.
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        raw = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        logger.warning("extraction: could not parse LLM output as JSON")
        return []
    if not isinstance(raw, list):
        return []

    candidates: list[tuple[MemoryCategory, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        category_raw = str(item.get("category", "")).strip().lower()
        if not content:
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
    trigger_token_threshold: int = SUMMARY_TRIGGER_TOKEN_THRESHOLD,
    trigger_message_count: int = SUMMARY_TRIGGER_MESSAGE_COUNT,
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

    delta_tokens = sum(estimate_tokens(m.content) for m in delta)
    if (
        delta_tokens < trigger_token_threshold
        and len(delta) < trigger_message_count
    ):
        return []  # not due yet; leave the watermark untouched

    # Advance the watermark first (on the still-fresh instance). memory_service
    # commits below, persisting this too; on an LLM failure the whole unit of work
    # rolls back, so the window is retried rather than silently skipped.
    target_seq = delta[-1].seq
    await conv_repo.set_extraction_watermark(
        session, conversation, seq=target_seq
    )

    transcript = "\n".join(f"{m.role.value}: {m.content}" for m in delta)
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
        await src_repo.link_source(
            session,
            user_id=user_id,
            memory_id=memory.id,
            conversation_id=conversation_id,
            source_kind=SourceKind.CONVERSATION,
        )
        created.append(memory)
    return created
