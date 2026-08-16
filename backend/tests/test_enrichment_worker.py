"""Background enrichment worker tests (M5): end-to-end consumers, isolation, idle."""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models.enums import MessageRole, SummaryType
from app.repositories import conversation_repository as conv_repo
from app.repositories import conversation_summary_repository as sum_repo
from app.repositories import memory_repository as mem_repo
from app.repositories import memory_source_repository as src_repo
from app.repositories import message_repository as msg_repo
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.llm.base import LLMResponse
from app.services.llm.fake_provider import FakeLLMProvider
from app.workers.enrichment_worker import EnrichmentWorker


class _RaisingLLM:
    name = "raising"

    async def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        raise RuntimeError("boom")


async def _seed_conversation(
    maker: async_sessionmaker[AsyncSession], user_id: uuid.UUID, messages: int
) -> uuid.UUID:
    async with maker() as session:
        conv = await conv_repo.create_conversation(session, user_id=user_id)
        await session.flush()
        for i in range(messages):
            await msg_repo.append_message(
                session,
                conversation_id=conv.id,
                user_id=user_id,
                role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
                content="discuss the project roadmap",
            )
        await session.commit()
        return conv.id


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


async def test_worker_runs_title_and_summary(
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    seed_user: uuid.UUID,
) -> None:
    conv_id = await _seed_conversation(sessionmaker_fixture, seed_user, messages=6)
    worker = EnrichmentWorker()
    worker.configure(
        sessionmaker=sessionmaker_fixture,
        llm=FakeLLMProvider(reply="Generated Text"),
        embedding_service=_embeddings(),
    )
    worker.start()
    worker.enqueue(conv_id, seed_user)
    await asyncio.wait_for(worker.join(), timeout=5)
    await worker.stop()

    async with sessionmaker_fixture() as session:
        conv = await conv_repo.get_conversation(
            session, conversation_id=conv_id, user_id=seed_user
        )
        assert conv is not None
        assert conv.title == "Generated Text"  # title consumer ran
        summary = await sum_repo.latest_summary(
            session,
            conversation_id=conv_id,
            user_id=seed_user,
            summary_type=SummaryType.ROLLING,
        )
        assert summary is not None  # rolling-summary consumer ran
        assert summary.content == "Generated Text"


async def test_worker_survives_failing_consumer(
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    seed_user: uuid.UUID,
) -> None:
    conv_id = await _seed_conversation(sessionmaker_fixture, seed_user, messages=6)
    worker = EnrichmentWorker()
    worker.configure(
        sessionmaker=sessionmaker_fixture,
        llm=_RaisingLLM(),
        embedding_service=_embeddings(),
    )
    worker.start()
    worker.enqueue(conv_id, seed_user)
    await asyncio.wait_for(worker.join(), timeout=5)

    assert worker.is_running  # a failing consumer did not crash the worker
    await worker.stop()

    async with sessionmaker_fixture() as session:
        conv = await conv_repo.get_conversation(
            session, conversation_id=conv_id, user_id=seed_user
        )
        assert conv is not None
        # Title is resilient to an LLM failure: it falls back to a snippet of
        # the first message rather than staying "Untitled".
        assert conv.title == "Discuss the project roadmap"
        # The summary consumer has no fallback, so its LLM failure writes nothing.
        summary = await sum_repo.latest_summary(
            session, conversation_id=conv_id, user_id=seed_user
        )
        assert summary is None


async def test_worker_extracts_memory_in_autonomous_mode(
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Consent gate: autonomous → the extraction consumer auto-saves.
    monkeypatch.setattr(get_settings(), "memory_consent_mode", "autonomous")
    conv_id = await _seed_conversation(sessionmaker_fixture, seed_user, messages=6)

    candidate = json.dumps([{"content": "Targeting Qualcomm", "category": "career"}])
    worker = EnrichmentWorker()
    worker.configure(
        sessionmaker=sessionmaker_fixture,
        llm=FakeLLMProvider(reply=candidate),
        embedding_service=_embeddings(),
    )
    worker.start()
    worker.enqueue(conv_id, seed_user)
    await asyncio.wait_for(worker.join(), timeout=5)
    await worker.stop()

    async with sessionmaker_fixture() as session:
        memories, total = await mem_repo.list_memories(
            session, user_id=seed_user, limit=10, offset=0
        )
        assert total == 1
        assert memories[0].content == "Targeting Qualcomm"
        links = await src_repo.list_for_memory(
            session, memory_id=memories[0].id, user_id=seed_user
        )
        assert len(links) == 1
        assert links[0].conversation_id == conv_id


async def test_worker_extracts_single_short_exchange(
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression (the "favorite football player" bug): a single short exchange
    # must be extracted per-turn, with no token/message threshold to clear.
    monkeypatch.setattr(get_settings(), "memory_consent_mode", "autonomous")
    conv_id = await _seed_conversation(sessionmaker_fixture, seed_user, messages=2)

    candidate = json.dumps(
        [
            {
                "content": "Favorite football player is Cristiano Ronaldo",
                "category": "preference",
            }
        ]
    )
    worker = EnrichmentWorker()
    worker.configure(
        sessionmaker=sessionmaker_fixture,
        llm=FakeLLMProvider(reply=candidate),
        embedding_service=_embeddings(),
    )
    worker.start()
    worker.enqueue(conv_id, seed_user)
    await asyncio.wait_for(worker.join(), timeout=5)
    await worker.stop()

    async with sessionmaker_fixture() as session:
        memories, total = await mem_repo.list_memories(
            session, user_id=seed_user, limit=10, offset=0
        )
        assert total == 1
        assert "Cristiano Ronaldo" in memories[0].content
        # Watermark advanced so the same fact is not re-extracted next turn.
        conv = await conv_repo.get_conversation(
            session, conversation_id=conv_id, user_id=seed_user
        )
        assert conv is not None and conv.last_extracted_seq == 2


async def test_worker_sets_tenant_context_for_consumers(
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: the worker MUST publish the tenant so the per-transaction GUC
    # is set and RLS lets consumers read/write on Postgres. (SQLite has no RLS,
    # so we assert the GUC source — get_current_user_id — directly.) Without the
    # fix this is None and every consumer silently no-ops in production.
    from app.core.tenant_context import get_current_user_id

    captured: dict[str, uuid.UUID | None] = {}

    async def _probe(
        session: AsyncSession,
        job: object,
        llm: object,
        embedding_service: object,
    ) -> None:
        captured["user_id"] = get_current_user_id()

    monkeypatch.setattr("app.workers.enrichment_worker.ENRICHMENT_CONSUMERS", (_probe,))
    conv_id = await _seed_conversation(sessionmaker_fixture, seed_user, messages=2)
    worker = EnrichmentWorker()
    worker.configure(
        sessionmaker=sessionmaker_fixture,
        llm=FakeLLMProvider(reply="x"),
        embedding_service=_embeddings(),
    )
    worker.start()
    worker.enqueue(conv_id, seed_user)
    await asyncio.wait_for(worker.join(), timeout=5)
    await worker.stop()

    assert captured["user_id"] == seed_user


async def test_enqueue_is_noop_when_idle() -> None:
    worker = EnrichmentWorker()
    worker.enqueue(uuid.uuid4(), uuid.uuid4())
    assert worker._queue.qsize() == 0
