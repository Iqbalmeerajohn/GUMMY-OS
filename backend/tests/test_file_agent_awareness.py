"""M6 agent awareness: uploaded-file *metadata* reaches the agent context pack.

Agents must see what the user uploaded (filename / type / status) but never the
file content — the context pack carries metadata only.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory
from app.services.agents import context_builder
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.files import file_service
from app.services.files.storage.local_provider import LocalFileStorage


async def _no_memories(*args, **kwargs) -> list[tuple[Memory, float]]:
    """Stub vector search (pgvector `<=>` is unavailable on SQLite)."""
    return []


async def test_context_pack_includes_file_metadata_only(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _no_memories,
    )
    storage = LocalFileStorage(str(tmp_path / "files"))
    await file_service.upload_file(
        db_session,
        user_id=seed_user,
        original_filename="resume.pdf.txt",
        content_type="text/plain",
        data=b"secret resume body that must not leak into agent context",
        storage=storage,
    )

    pack = await context_builder.build(
        db_session,
        user_id=seed_user,
        query="tell me about my files",
        embedding_service=EmbeddingService(FakeEmbeddingProvider()),
    )

    assert len(pack.files) == 1
    entry = pack.files[0]
    assert entry["filename"] == "resume.pdf.txt"
    assert entry["mime_type"] == "text/plain"
    assert entry["processing_status"] == "completed"
    # Metadata only — no raw content keys.
    assert "content" not in entry
    assert "secret resume body" not in str(entry)
