"""M6.5 File Intelligence: file context retrieval (search + attachment modes)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.files import file_context_service, file_service
from app.services.files.file_service import FileNotFoundError
from app.services.files.storage.local_provider import LocalFileStorage


@pytest.fixture
def storage(tmp_path) -> LocalFileStorage:
    return LocalFileStorage(str(tmp_path / "files"))


async def _upload(
    session: AsyncSession,
    user_id: uuid.UUID,
    storage: LocalFileStorage,
    name: str,
    body: bytes,
):
    return await file_service.upload_file(
        session,
        user_id=user_id,
        original_filename=name,
        content_type="text/plain",
        data=body,
        storage=storage,
    )


def test_extract_terms_drops_stopwords_and_short_tokens() -> None:
    terms = file_context_service.extract_terms(
        "What projects are mentioned in my resume?"
    )
    assert "projects" in terms
    assert "resume" in terms
    assert "what" not in terms  # stopword
    assert "in" not in terms  # too short / stopword


async def test_search_mode_returns_relevant_chunks(
    db_session: AsyncSession, seed_user: uuid.UUID, storage: LocalFileStorage
) -> None:
    await _upload(
        db_session,
        seed_user,
        storage,
        "resume.txt",
        b"Senior compiler engineer. Built Python projects and a resume parser.",
    )
    ctx = await file_context_service.retrieve_file_context(
        db_session,
        user_id=seed_user,
        query="What projects are in my resume?",
    )
    assert ctx.mode == "search"
    assert ctx.excerpts
    assert any("project" in e.content.lower() for e in ctx.excerpts)
    # Inventory is included for "what files do I have?" style questions.
    assert any(i["filename"] == "resume.txt" for i in ctx.inventory)


async def test_attachment_mode_uses_only_attached_files(
    db_session: AsyncSession, seed_user: uuid.UUID, storage: LocalFileStorage
) -> None:
    attached = await _upload(
        db_session, seed_user, storage, "a.txt", b"alpha content about widgets"
    )
    await _upload(
        db_session, seed_user, storage, "b.txt", b"beta content about gadgets"
    )
    ctx = await file_context_service.retrieve_file_context(
        db_session,
        user_id=seed_user,
        query="summarize this",  # no keyword overlap → proves attachment wins
        attached_file_ids=[attached.id],
    )
    assert ctx.mode == "attachment"
    assert ctx.excerpts
    # Only the attached file's content is present.
    assert all(e.file_id == attached.id for e in ctx.excerpts)
    assert any("widgets" in e.content for e in ctx.excerpts)
    assert not any("gadgets" in e.content for e in ctx.excerpts)


async def test_attachment_foreign_file_raises_404(
    db_session: AsyncSession, seed_user: uuid.UUID, storage: LocalFileStorage
) -> None:
    foreign = await _upload(db_session, seed_user, storage, "mine.txt", b"private")
    with pytest.raises(FileNotFoundError):
        await file_context_service.retrieve_file_context(
            db_session,
            user_id=uuid.uuid4(),  # different tenant
            query="summarize",
            attached_file_ids=[foreign.id],
        )


async def test_search_scoped_to_tenant(
    db_session: AsyncSession, seed_user: uuid.UUID, storage: LocalFileStorage
) -> None:
    await _upload(db_session, seed_user, storage, "secret.txt", b"confidential roadmap")
    ctx = await file_context_service.retrieve_file_context(
        db_session,
        user_id=uuid.uuid4(),  # foreign tenant sees nothing
        query="roadmap",
    )
    assert ctx.excerpts == []
    assert ctx.inventory == []


async def test_render_file_context_empty_is_none() -> None:
    empty = file_context_service.FileContext(mode="none")
    assert file_context_service.render_file_context(empty) is None
