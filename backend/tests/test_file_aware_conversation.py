"""M6.5: file-aware conversations — uploaded content reaches the LLM prompt.

Drives the grounded reply core with a capturing fake LLM and asserts that file
content (search mode) and attached-file content (attachment mode) land in the
system prompt. Memory vector search is monkeypatched (pgvector is unavailable on
the SQLite test DB), matching the existing turn tests.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.services.conversation import conversation_turn_service
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.files import file_service
from app.services.files.storage.local_provider import LocalFileStorage
from app.services.llm.fake_provider import FakeLLMProvider


@pytest.fixture
def storage(tmp_path) -> LocalFileStorage:
    return LocalFileStorage(str(tmp_path / "files"))


@pytest.fixture(autouse=True)
def _no_vector_search(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _empty(*args, **kwargs) -> list[tuple[Memory, float]]:
        return []

    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _empty
    )


def _embeddings() -> EmbeddingService:
    return EmbeddingService(FakeEmbeddingProvider())


async def _upload(session, user_id, storage, name, body):
    return await file_service.upload_file(
        session,
        user_id=user_id,
        original_filename=name,
        content_type="text/plain",
        data=body,
        storage=storage,
    )


async def test_reply_grounds_in_uploaded_file_via_search(
    db_session: AsyncSession, seed_user: uuid.UUID, storage: LocalFileStorage
) -> None:
    await _upload(
        db_session,
        seed_user,
        storage,
        "ResumeGUM.txt",
        b"Experienced backend engineer. Led several GUMMY OS compiler projects.",
    )
    llm = FakeLLMProvider(reply="ok")
    await conversation_turn_service.generate_grounded_reply(
        db_session,
        user_id=seed_user,
        message="What projects are mentioned in my resume?",
        embedding_service=_embeddings(),
        llm=llm,
    )
    system = str(llm.calls[-1]["system"])
    # M7: file grounding now lands inside the unified <knowledge> block.
    assert "<knowledge>" in system
    assert "compiler projects" in system
    assert "ResumeGUM.txt" in system


async def test_attachment_only_uses_attached_file(
    db_session: AsyncSession, seed_user: uuid.UUID, storage: LocalFileStorage
) -> None:
    attached = await _upload(
        db_session, seed_user, storage, "report.txt", b"Quarterly revenue up 30%."
    )
    await _upload(
        db_session, seed_user, storage, "other.txt", b"Unrelated cooking recipes."
    )
    llm = FakeLLMProvider(reply="ok")
    await conversation_turn_service.generate_grounded_reply(
        db_session,
        user_id=seed_user,
        message="Summarize this document",
        embedding_service=_embeddings(),
        llm=llm,
        attachment_file_ids=[attached.id],
    )
    system = str(llm.calls[-1]["system"])
    assert "Quarterly revenue up 30%" in system
    assert "cooking recipes" not in system


async def test_file_awareness_inventory_in_prompt(
    db_session: AsyncSession, seed_user: uuid.UUID, storage: LocalFileStorage
) -> None:
    await _upload(db_session, seed_user, storage, "notes.txt", b"some notes")
    llm = FakeLLMProvider(reply="ok")
    await conversation_turn_service.generate_grounded_reply(
        db_session,
        user_id=seed_user,
        message="What files do I have?",
        embedding_service=_embeddings(),
        llm=llm,
    )
    system = str(llm.calls[-1]["system"])
    assert "Uploaded files:" in system
    assert "notes.txt" in system


async def test_no_files_keeps_prompt_clean(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    llm = FakeLLMProvider(reply="ok")
    await conversation_turn_service.generate_grounded_reply(
        db_session,
        user_id=seed_user,
        message="Hello there",
        embedding_service=_embeddings(),
        llm=llm,
    )
    system = str(llm.calls[-1]["system"])
    # No memories, goals, or files → the unified <knowledge> block is omitted.
    assert "<knowledge>" not in system
    assert "<files>" not in system


async def test_stream_turn_injects_file_context(
    db_session: AsyncSession, seed_user: uuid.UUID, storage: LocalFileStorage
) -> None:
    from app.repositories import conversation_repository as conv_repo

    conversation = await conv_repo.create_conversation(db_session, user_id=seed_user)
    await db_session.commit()
    await _upload(
        db_session,
        seed_user,
        storage,
        "spec.txt",
        b"The widget API supports rate limiting and retries.",
    )
    llm = FakeLLMProvider(reply="done")
    events = []
    async for ev in conversation_turn_service.stream_turn(
        db_session,
        user_id=seed_user,
        conversation_id=conversation.id,
        message="What does my spec say about rate limiting?",
        embedding_service=_embeddings(),
        llm=llm,
    ):
        events.append(ev)
    # The first turn also generates a title via the LLM, so scan all calls for
    # the reply prompt that carries the file context.
    systems = [str(c["system"]) for c in llm.calls]
    assert any("rate limiting and retries" in s for s in systems)
    assert events[-1]["type"] == "done"
