"""Unified knowledge retrieval tests (M7) — fan-out, attribution, isolation.

Covers the retrieval layer end to end against the in-memory DB: memories + goals
+ files retrieved together, provenance recorded, attachment priority, and the
graceful-degradation contract (no single source can take a turn down).
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory
from app.models.memory import Memory
from app.repositories import goal_repository
from app.repositories import memory_repository as mem_repo
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.files import file_service
from app.services.files.storage.local_provider import LocalFileStorage
from app.services.knowledge import knowledge_ranker, knowledge_retrieval_service
from app.services.knowledge.knowledge_retrieval_service import (
    SOURCE_FILE,
    SOURCE_GOAL,
    SOURCE_MEMORY,
)


@pytest.fixture
def storage(tmp_path) -> LocalFileStorage:
    return LocalFileStorage(str(tmp_path / "files"))


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


async def _fake_search(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query_vector: list[float],
    embedding_model: str,
    limit: int,
    include_archived: bool = False,
    category: MemoryCategory | None = None,
) -> list[tuple[Memory, float]]:
    items, _ = await mem_repo.list_memories(
        session, user_id=user_id, limit=limit, offset=0
    )
    return [(memory, 0.1 * index) for index, memory in enumerate(items)]


async def _seed_memory(session: AsyncSession, user_id: uuid.UUID) -> None:
    await mem_repo.create_memory(
        session,
        user_id=user_id,
        category=MemoryCategory.CAREER,
        content="Targeting an AI Engineer role",
        importance_score=0.8,
        confidence_score=0.8,
    )
    await session.commit()


async def _seed_goal(session: AsyncSession, user_id: uuid.UUID) -> None:
    await goal_repository.create_goal(
        session, user_id=user_id, title="Get an AI Engineer job"
    )
    await session.commit()


async def _upload(session, user_id, storage, name, body):
    return await file_service.upload_file(
        session,
        user_id=user_id,
        original_filename=name,
        content_type="text/plain",
        data=body,
        storage=storage,
    )


# ── Fan-out + attribution ─────────────────────────────────────────────────────


async def test_retrieves_all_three_sources_with_provenance(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    storage: LocalFileStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _seed_memory(db_session, seed_user)
    await _seed_goal(db_session, seed_user)
    await _upload(
        db_session, seed_user, storage, "resume.txt", b"Built AI Engineer projects."
    )

    ctx = await knowledge_retrieval_service.retrieve(
        db_session,
        user_id=seed_user,
        query="AI Engineer projects",
        embedding_service=_embeddings(),
    )

    assert ctx.memories and all(i.source == SOURCE_MEMORY for i in ctx.memories)
    assert ctx.goals and all(i.source == SOURCE_GOAL for i in ctx.goals)
    assert ctx.files and all(i.source == SOURCE_FILE for i in ctx.files)
    assert set(ctx.sources_used) == {SOURCE_MEMORY, SOURCE_GOAL, SOURCE_FILE}


# ── Attachment priority ───────────────────────────────────────────────────────


async def test_attachment_ranks_above_memory_and_goal(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    storage: LocalFileStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _seed_memory(db_session, seed_user)
    await _seed_goal(db_session, seed_user)
    attached = await _upload(
        db_session, seed_user, storage, "report.txt", b"Quarterly revenue up 30%."
    )
    await _upload(
        db_session, seed_user, storage, "other.txt", b"Unrelated cooking recipes."
    )

    ctx = await knowledge_retrieval_service.retrieve(
        db_session,
        user_id=seed_user,
        query="summarize this",
        embedding_service=_embeddings(),
        attachment_file_ids=[attached.id],
    )
    ranked = knowledge_ranker.rank(ctx)

    # The attached file leads the fused ranking…
    assert ranked[0].source == SOURCE_FILE
    assert ranked[0].metadata["attached"] is True
    # …and only the attached file's content is present (no other-file content).
    joined = " ".join(i.content for i in ctx.files)
    assert "revenue" in joined
    assert "cooking recipes" not in joined


# ── Graceful degradation: no source can take a turn down ──────────────────────


async def test_memory_failure_degrades_to_goals_and_files(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    storage: LocalFileStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(*args, **kwargs):
        raise RuntimeError("memory backend down")

    monkeypatch.setattr(
        "app.services.memory.memory_retrieval_service.retrieve_memories", _boom
    )
    await _seed_goal(db_session, seed_user)
    await _upload(db_session, seed_user, storage, "notes.txt", b"some notes here")

    ctx = await knowledge_retrieval_service.retrieve(
        db_session,
        user_id=seed_user,
        query="anything",
        embedding_service=_embeddings(),
    )
    assert ctx.memories == []
    assert ctx.goals  # goals still retrieved
    assert SOURCE_MEMORY not in ctx.sources_used


async def test_goal_failure_is_savepoint_isolated(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom_list_active(session, *, user_id, limit):
        # Real failing SQL exercises the transaction-poisoning path.
        await session.execute(sa.text("SELECT * FROM __missing_goal_table__"))
        return []

    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    monkeypatch.setattr(
        "app.repositories.goal_repository.list_active", _boom_list_active
    )
    await _seed_memory(db_session, seed_user)

    ctx = await knowledge_retrieval_service.retrieve(
        db_session,
        user_id=seed_user,
        query="anything",
        embedding_service=_embeddings(),
    )
    assert ctx.goals == []
    assert ctx.memories  # memory still works
    # The savepoint confined the failure — the outer transaction is still usable.
    assert (await db_session.execute(sa.text("SELECT 1"))).scalar() == 1


async def test_file_search_failure_degrades_to_memory_and_goals(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _boom(*args, **kwargs):
        raise RuntimeError("files backend down")

    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    monkeypatch.setattr(
        "app.services.files.file_context_service.retrieve_file_context", _boom
    )
    await _seed_memory(db_session, seed_user)
    await _seed_goal(db_session, seed_user)

    ctx = await knowledge_retrieval_service.retrieve(
        db_session,
        user_id=seed_user,
        query="anything",
        embedding_service=_embeddings(),
    )
    assert ctx.files == []
    assert ctx.memories and ctx.goals
    assert SOURCE_FILE not in ctx.sources_used


# ── PostHog analytics (M7 event family) ───────────────────────────────────────


async def test_emits_knowledge_analytics_events(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    storage: LocalFileStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict]] = []

    def _record(*, distinct_id, event, properties=None):
        events.append((event, properties or {}))

    monkeypatch.setattr("app.observability.analytics.capture_event", _record)
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _fake_search
    )
    await _seed_memory(db_session, seed_user)
    attached = await _upload(
        db_session, seed_user, storage, "resume.txt", b"AI Engineer resume."
    )

    await knowledge_retrieval_service.retrieve(
        db_session,
        user_id=seed_user,
        query="summarize",
        embedding_service=_embeddings(),
        attachment_file_ids=[attached.id],
    )

    names = {e for e, _ in events}
    assert "KnowledgeRetrieved" in names
    assert "KnowledgeSourceUsed" in names
    assert "KnowledgeAttachmentUsed" in names
