"""Background enrichment worker tests (M5): end-to-end consumers, isolation, idle."""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import MessageRole, SummaryType
from app.repositories import conversation_repository as conv_repo
from app.repositories import conversation_summary_repository as sum_repo
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
            session, conversation_id=conv_id, user_id=seed_user,
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
        assert conv.title is None  # nothing was written
        summary = await sum_repo.latest_summary(
            session, conversation_id=conv_id, user_id=seed_user
        )
        assert summary is None


async def test_enqueue_is_noop_when_idle() -> None:
    worker = EnrichmentWorker()
    worker.enqueue(uuid.uuid4(), uuid.uuid4())
    assert worker._queue.qsize() == 0
