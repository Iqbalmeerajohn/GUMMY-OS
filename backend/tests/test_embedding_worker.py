"""Background embedding worker tests: processing, retries, idle no-op."""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import MemoryCategory
from app.repositories import memory_embedding_repository as embed_repo
from app.repositories import memory_repository as repo
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.workers.embedding_worker import EmbeddingWorker


class _RaisingProvider:
    model_name = "raising"
    dimension = 384

    def embed_text(self, text: str) -> list[float]:
        raise RuntimeError("boom")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("boom")


async def _seed_memory(
    maker: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> uuid.UUID:
    async with maker() as session:
        memory = await repo.create_memory(
            session,
            user_id=user_id,
            category=MemoryCategory.PROFILE,
            content="hello",
            importance_score=0.5,
            confidence_score=0.5,
        )
        await session.commit()
        return memory.id


async def test_worker_processes_job(
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    seed_user: uuid.UUID,
) -> None:
    memory_id = await _seed_memory(sessionmaker_fixture, seed_user)
    worker = EmbeddingWorker(max_retries=2, retry_base_delay=0.0)
    worker.configure(
        sessionmaker=sessionmaker_fixture,
        embedding_service=EmbeddingService(FakeEmbeddingProvider()),
    )
    worker.start()
    worker.enqueue(memory_id, seed_user)
    await asyncio.wait_for(worker.join(), timeout=5)
    await worker.stop()

    async with sessionmaker_fixture() as session:
        rows = await embed_repo.list_embeddings(session, memory_id=memory_id)
    assert len(rows) == 1


async def test_worker_survives_failing_job(
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    seed_user: uuid.UUID,
) -> None:
    memory_id = await _seed_memory(sessionmaker_fixture, seed_user)
    worker = EmbeddingWorker(max_retries=2, retry_base_delay=0.0)
    worker.configure(
        sessionmaker=sessionmaker_fixture,
        embedding_service=EmbeddingService(_RaisingProvider()),
    )
    worker.start()
    worker.enqueue(memory_id, seed_user)
    await asyncio.wait_for(worker.join(), timeout=5)

    assert worker.is_running  # failure did not crash the worker
    await worker.stop()

    async with sessionmaker_fixture() as session:
        rows = await embed_repo.list_embeddings(session, memory_id=memory_id)
    assert rows == []  # no embedding written


async def test_enqueue_is_noop_when_idle() -> None:
    worker = EmbeddingWorker()
    worker.enqueue(uuid.uuid4(), uuid.uuid4())
    assert worker._queue.qsize() == 0
