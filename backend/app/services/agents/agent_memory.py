"""Shared Agent Memory Access — the one door agents have into memory (M7).

A thin facade over the Phase 1 Memory Engine and Phase 2 provenance: no
scoring, versioning, embedding, or retrieval logic is reimplemented here.

- ``recall`` → ``memory_retrieval_service`` (hybrid retrieval; read = Green).
- ``propose`` → the **consent gate** (the exact ``ConsentMode`` semantics
  Phase 2 extraction ships) → ``memory_service.create_memory`` →
  ``memory_source_repository.link_source(source_kind='agent')``.

``memory_service.create_memory`` owns its commit, so ``propose`` must run
**post-commit of the turn** (run_turn calls it after its unit of work, like
enrichment dispatch) — never inside the orchestration transaction.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.constants import EXTRACTION_MAX_MEMORIES
from app.models.enums import ConsentMode, MemoryCategory, SourceKind
from app.models.memory import Memory
from app.repositories import memory_source_repository as src_repo
from app.schemas.memory import MemoryCreate
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.memory import memory_retrieval_service, memory_service
from app.services.memory.memory_retrieval_service import RankedMemory

logger = logging.getLogger(__name__)

# Categories that must never be auto-saved (mirrors extraction's guard).
_SENSITIVE_CATEGORIES: frozenset[MemoryCategory] = frozenset()


def _resolve_consent(consent_mode: ConsentMode | None) -> ConsentMode:
    if consent_mode is not None:
        return consent_mode
    try:
        return ConsentMode(get_settings().memory_consent_mode.lower())
    except ValueError:
        return ConsentMode.ASSISTED  # safe default


async def recall(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query: str,
    embedding_service: EmbeddingService,
    limit: int,
) -> list[RankedMemory]:
    """Scoped hybrid retrieval (read path; Green). Pure delegation."""
    return await memory_retrieval_service.retrieve_memories(
        session,
        user_id=user_id,
        query=query,
        embedding_service=embedding_service,
        limit=limit,
    )


def _validate_candidates(
    candidates: list[dict],
) -> list[tuple[MemoryCategory, str]]:
    """Validate agent-proposed candidates into (category, content) pairs."""
    valid: list[tuple[MemoryCategory, str]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        try:
            category = MemoryCategory(
                str(item.get("category", "")).strip().lower()
            )
        except ValueError:
            continue
        if category in _SENSITIVE_CATEGORIES:
            continue
        valid.append((category, content))
    return valid


async def propose(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    candidates: list[dict],
    agent_key: str,
    conversation_id: uuid.UUID | None = None,
    consent_mode: ConsentMode | None = None,
) -> list[Memory]:
    """Persist agent-proposed memories through the consent gate.

    Only ``autonomous`` consent persists; ``assisted``/``explicit`` save
    nothing (the proposal surface is future work — identical to Phase 2
    extraction). Every saved memory routes through ``memory_service`` (its
    own commit; call post-turn-commit only) and records
    ``source_kind='agent'`` provenance.
    """
    mode = _resolve_consent(consent_mode)
    if mode is not ConsentMode.AUTONOMOUS:
        return []

    created: list[Memory] = []
    for category, content in _validate_candidates(candidates)[
        :EXTRACTION_MAX_MEMORIES
    ]:
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
            source_kind=SourceKind.AGENT,
        )
        await session.commit()  # the link rides the memory's unit of work
        created.append(memory)
        logger.info(
            "agent %s proposed memory %s (category=%s)",
            agent_key,
            memory.id,
            category.value,
        )
    return created
