"""Relevance-gating tests for memory retrieval.

The guarantee under test is narrow and important: **a memory that is not about
the query must not reach the model**, however important, confident, or recent it
is. Before the relevance floor, retrieval sorted by a blended score and took the
top N unconditionally, so a question with no relevant memories still got the
user's most important ones injected — which is what made the assistant volunteer
facts nobody asked about.

pgvector is PostgreSQL-only, so candidate fetch is monkeypatched (the established
pattern in test_memory_e2e). That is exactly the right seam here: these tests are
about what retrieval *does with* similarity scores, so supplying them directly is
more precise than hoping a real embedding model produces the case under test.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    EMBEDDING_DIMENSION,
    RETRIEVAL_MIN_SEMANTIC_SIMILARITY,
)
from app.models.enums import MemoryCategory, MemoryStatus
from app.models.memory import Memory
from app.repositories import memory_repository as repo
from app.repositories.search_repository import build_search_statement
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.memory import memory_retrieval_service
from app.services.memory.memory_retrieval_service import (
    compute_recency_score,
    recency_reference,
    retrieve_memories,
)


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider(dimension=8))


async def _memory(
    session: AsyncSession,
    user_id: uuid.UUID,
    content: str,
    *,
    category: MemoryCategory = MemoryCategory.PROFILE,
    importance: float = 0.5,
    confidence: float = 0.5,
) -> Memory:
    memory = await repo.create_memory(
        session,
        user_id=user_id,
        category=category,
        content=content,
        importance_score=importance,
        confidence_score=confidence,
    )
    await session.commit()
    return memory


def _fake_search_returning(
    pairs: list[tuple[Memory, float]],
) -> Callable[..., Awaitable[list[tuple[Memory, float]]]]:
    """A candidate fetcher that yields exactly these (memory, distance) pairs."""

    async def _search(
        session: AsyncSession, **kwargs: Any
    ) -> list[tuple[Memory, float]]:
        limit = int(kwargs.get("limit", len(pairs)))
        return pairs[:limit]

    return _search


def _similarity_to_distance(similarity: float) -> float:
    """The retriever computes similarity as ``1 - distance``; invert for setup."""
    return 1.0 - similarity


# ── The floor ────────────────────────────────────────────────────────────────


async def test_relevant_memory_is_retrieved(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = await _memory(db_session, seed_user, "Lives in Vizag, India")
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search_returning([(memory, _similarity_to_distance(0.80))]),
    )

    results = await retrieve_memories(
        db_session,
        user_id=seed_user,
        query="where do I live?",
        embedding_service=_embeddings(),
        reinforce=False,
    )

    assert [r.memory.content for r in results] == ["Lives in Vizag, India"]


async def test_irrelevant_memory_is_rejected(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Below the floor → nothing is returned, not "the best of a bad set"."""
    memory = await _memory(db_session, seed_user, "Favorite sport is football")
    below = RETRIEVAL_MIN_SEMANTIC_SIMILARITY - 0.05
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search_returning([(memory, _similarity_to_distance(below))]),
    )

    results = await retrieve_memories(
        db_session,
        user_id=seed_user,
        query="what is the capital of France?",
        embedding_service=_embeddings(),
        reinforce=False,
    )

    assert results == []


async def test_importance_cannot_rescue_an_irrelevant_memory(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The regression this floor exists to prevent.

    Importance, confidence, and recency carry 45% of the blended score — enough,
    before the floor, to lift a topically unrelated memory into the top N. The
    gate is applied to raw semantic similarity precisely so that cannot happen.
    """
    memory = await _memory(
        db_session,
        seed_user,
        "Building GUMMY, a personal AI operating system",
        category=MemoryCategory.PROJECT,
        importance=1.0,
        confidence=1.0,
    )
    below = RETRIEVAL_MIN_SEMANTIC_SIMILARITY - 0.01
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search_returning([(memory, _similarity_to_distance(below))]),
    )

    results = await retrieve_memories(
        db_session,
        user_id=seed_user,
        query="explain the quicksort algorithm",
        embedding_service=_embeddings(),
        reinforce=False,
    )

    assert results == []


async def test_important_and_relevant_memory_is_retained(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The floor must not make GUMMY forgetful: clearing it is enough to stay."""
    important = await _memory(
        db_session, seed_user, "Name is Iqbal", importance=0.9, confidence=0.9
    )
    ordinary = await _memory(
        db_session, seed_user, "Favorite sport is football", importance=0.2
    )
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search_returning(
            [
                (important, _similarity_to_distance(0.62)),
                (ordinary, _similarity_to_distance(0.60)),
            ]
        ),
    )

    results = await retrieve_memories(
        db_session,
        user_id=seed_user,
        query="what is my name?",
        embedding_service=_embeddings(),
        reinforce=False,
    )

    assert [r.memory.content for r in results][0] == "Name is Iqbal"
    assert len(results) == 2


async def test_floor_can_be_overridden_for_diagnostics(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``min_semantic=0.0`` shows rejected candidates (the diagnostics view)."""
    memory = await _memory(db_session, seed_user, "Favorite sport is football")
    below = RETRIEVAL_MIN_SEMANTIC_SIMILARITY - 0.2
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search_returning([(memory, _similarity_to_distance(below))]),
    )

    results = await retrieve_memories(
        db_session,
        user_id=seed_user,
        query="unrelated",
        embedding_service=_embeddings(),
        reinforce=False,
        min_semantic=0.0,
    )

    assert len(results) == 1


# ── Deduplication ────────────────────────────────────────────────────────────


async def test_duplicate_memories_are_collapsed(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live store really does hold this fact twice (pre-consolidation)."""
    first = await _memory(
        db_session,
        seed_user,
        "Building GUMMY, a personal AI operating system",
        category=MemoryCategory.PROJECT,
    )
    second = await _memory(
        db_session,
        seed_user,
        "Building GUMMY, a personal AI operating system",
        category=MemoryCategory.PROJECT,
    )
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search_returning(
            [
                (first, _similarity_to_distance(0.80)),
                (second, _similarity_to_distance(0.79)),
            ]
        ),
    )

    results = await retrieve_memories(
        db_session,
        user_id=seed_user,
        query="what am I building?",
        embedding_service=_embeddings(),
        reinforce=False,
    )

    assert len(results) == 1


async def test_dedupe_ignores_case_and_punctuation(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = await _memory(db_session, seed_user, "Name is Iqbal")
    second = await _memory(db_session, seed_user, "name is iqbal.")
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search_returning(
            [
                (first, _similarity_to_distance(0.80)),
                (second, _similarity_to_distance(0.78)),
            ]
        ),
    )

    results = await retrieve_memories(
        db_session,
        user_id=seed_user,
        query="what is my name?",
        embedding_service=_embeddings(),
        reinforce=False,
    )

    assert len(results) == 1


async def test_distinct_memories_are_both_kept(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dedup must not swallow genuinely different facts."""
    first = await _memory(db_session, seed_user, "Lives in Bangalore")
    second = await _memory(db_session, seed_user, "Name is Iqbal")
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search_returning(
            [
                (first, _similarity_to_distance(0.80)),
                (second, _similarity_to_distance(0.78)),
            ]
        ),
    )

    results = await retrieve_memories(
        db_session,
        user_id=seed_user,
        query="tell me about myself",
        embedding_service=_embeddings(),
        reinforce=False,
    )

    assert len(results) == 2


# ── Lifecycle exclusion (asserted on the real SQL, not the fake) ─────────────


def _compiled_sql(*, include_archived: bool) -> str:
    """The real search statement as SQL.

    ``literal_binds`` needs a correctly-sized vector — pgvector validates the
    width while rendering the literal, so a stub-length vector fails to compile.
    """
    stmt = build_search_statement(
        user_id=uuid.uuid4(),
        query_vector=[0.0] * EMBEDDING_DIMENSION,
        embedding_model="fake",
        limit=10,
        include_archived=include_archived,
    )
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def test_superseded_and_archived_memories_are_excluded_by_the_query() -> None:
    """Lifecycle filtering lives in SQL, so it is asserted against the SQL.

    Monkeypatching candidate fetch would bypass exactly the predicate under
    test, so this compiles the real statement instead.
    """
    sql = _compiled_sql(include_archived=False)

    # status = 'active' excludes BOTH superseded and archived in one predicate.
    assert "memories.deleted_at IS NULL" in sql
    assert f"memories.status = '{MemoryStatus.ACTIVE.value}'" in sql
    assert MemoryStatus.SUPERSEDED.value not in sql


def test_archived_memories_are_included_only_when_asked() -> None:
    sql = _compiled_sql(include_archived=True)

    # The status predicate is dropped, but soft-deleted rows stay excluded.
    assert f"memories.status = '{MemoryStatus.ACTIVE.value}'" not in sql
    assert "memories.deleted_at IS NULL" in sql


async def test_soft_deleted_memory_is_not_returned_by_the_repository(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    memory = await _memory(db_session, seed_user, "Temporary fact")
    await repo.delete_memory(db_session, memory)
    await db_session.commit()

    assert (
        await repo.get_memory(db_session, memory_id=memory.id, user_id=seed_user)
        is None
    )


# ── Recency semantics ────────────────────────────────────────────────────────


async def test_recency_is_measured_from_when_the_fact_was_learned(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Not from ``last_recalled_at`` — that formed a self-reinforcing loop.

    Retrieval stamps ``last_recalled_at`` on everything it surfaces, so scoring
    recency from it meant a retrieved memory reset to maximum recency and became
    more likely to be retrieved again, regardless of continued relevance.
    """
    memory = await _memory(db_session, seed_user, "Name is Iqbal")
    memory.last_recalled_at = datetime.now(UTC)

    assert recency_reference(memory) == memory.created_at


async def test_event_memories_decay_from_when_they_happened(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """An event imported today about last year should score as last year."""
    memory = await _memory(db_session, seed_user, "Attended a conference")
    long_ago = datetime.now(UTC) - timedelta(days=365)
    memory.occurred_at = long_ago

    assert recency_reference(memory) == long_ago

    now = datetime.now(UTC)
    assert compute_recency_score(recency_reference(memory), now=now) < 0.01


async def test_retrieval_does_not_inflate_recency_on_repeat(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two retrievals of the same memory produce the same recency score."""
    memory = await _memory(db_session, seed_user, "Name is Iqbal")
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search_returning([(memory, _similarity_to_distance(0.80))]),
    )

    first = await retrieve_memories(
        db_session,
        user_id=seed_user,
        query="what is my name?",
        embedding_service=_embeddings(),
        reinforce=True,
    )
    second = await retrieve_memories(
        db_session,
        user_id=seed_user,
        query="what is my name?",
        embedding_service=_embeddings(),
        reinforce=True,
    )

    assert first[0].recency_score == pytest.approx(second[0].recency_score, abs=1e-6)


# ── Provenance survives retrieval ───────────────────────────────────────────


async def test_provenance_is_retained_through_retrieval(
    db_session: AsyncSession, seed_user: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retrieval returns the ORM row, so its source links stay reachable."""
    from app.models.enums import SourceKind
    from app.repositories import memory_source_repository as src_repo

    memory = await _memory(db_session, seed_user, "Name is Iqbal")
    await src_repo.link_source(
        db_session,
        user_id=seed_user,
        memory_id=memory.id,
        conversation_id=None,
        source_kind=SourceKind.AGENT,
    )
    await db_session.commit()

    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search_returning([(memory, _similarity_to_distance(0.80))]),
    )
    results = await retrieve_memories(
        db_session,
        user_id=seed_user,
        query="what is my name?",
        embedding_service=_embeddings(),
        reinforce=False,
    )

    sources = await src_repo.list_for_memory(
        db_session, memory_id=results[0].memory.id, user_id=seed_user
    )
    assert len(sources) == 1
    assert sources[0].source_kind is SourceKind.AGENT


# ── The guidance the model receives ─────────────────────────────────────────


def test_knowledge_guidance_instructs_silent_use() -> None:
    """Retrieval gating is half the fix; the other half is telling the model
    not to narrate what it retrieved."""
    from app.services.memory.prompt_builder import _KNOWLEDGE_GUIDANCE

    lowered = _KNOWLEDGE_GUIDANCE.lower()
    assert "silently" in lowered
    assert "as you told me before" in lowered
    assert "ignore it entirely" in lowered


def test_memory_retrieval_service_exposes_the_floor() -> None:
    assert 0.0 < RETRIEVAL_MIN_SEMANTIC_SIMILARITY < 1.0
    assert memory_retrieval_service.RETRIEVAL_MIN_SEMANTIC_SIMILARITY == (
        RETRIEVAL_MIN_SEMANTIC_SIMILARITY
    )
