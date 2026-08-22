"""doc_read: reading one of the user's own documents by name.

This was a stub returning ``{"found": False}`` because the document store
arrived after the tool. The behaviour worth pinning is not that it reads, but
what it refuses to do: resolve someone else's document, invent a location, or
pour an entire PDF into the context window.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProcessingStatus, UploadStatus
from app.repositories import file_chunk_repository as chunk_repo
from app.repositories import file_repository as file_repo
from app.services.agents.tools import doc_read
from app.services.agents.tools.context import ToolContext


async def _document(
    session: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    chunks: list[dict],
) -> uuid.UUID:
    file = await file_repo.create_file(
        session,
        user_id=user_id,
        filename=name,
        original_filename=name,
        mime_type="text/plain",
        size_bytes=100,
        storage_path=f"{user_id}/{name}",
        upload_status=UploadStatus.UPLOADED,
        processing_status=ProcessingStatus.COMPLETED,
    )
    await chunk_repo.bulk_create_chunks(
        session, user_id=user_id, file_id=file.id, chunks=chunks
    )
    await session.commit()
    return file.id


def _chunk(i: int, content: str, meta: dict | None = None) -> dict:
    return {
        "chunk_index": i,
        "content": content,
        "token_count": 10,
        "metadata_json": meta,
    }


async def test_resolves_a_document_by_partial_case_insensitive_name(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """A model asked about "my resume" says exactly that, not a UUID."""
    await _document(db_session, seed_user, "Resume.pdf", [_chunk(0, "experience")])
    result = await doc_read.execute(
        ToolContext(session=db_session, user_id=seed_user), {"ref": "resume"}
    )
    assert result["found"] is True
    assert result["filename"] == "Resume.pdf"


async def test_a_missing_document_is_data_not_an_error(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """ "You have no such document" is a real answer the model should give."""
    result = await doc_read.execute(
        ToolContext(session=db_session, user_id=seed_user), {"ref": "nothing"}
    )
    assert result["found"] is False
    assert result["content"] is None


async def test_another_users_document_does_not_resolve(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """Ownership comes from the context, so a known filename is not a key."""
    await _document(db_session, seed_user, "Secret.pdf", [_chunk(0, "salary 184000")])
    result = await doc_read.execute(
        ToolContext(session=db_session, user_id=uuid.uuid4()), {"ref": "Secret.pdf"}
    )
    assert result["found"] is False


async def test_page_labels_come_from_extraction(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    await _document(
        db_session,
        seed_user,
        "Paged.pdf",
        [_chunk(0, "first page text", {"page": 1})],
    )
    result = await doc_read.execute(
        ToolContext(session=db_session, user_id=seed_user), {"ref": "Paged"}
    )
    assert "[page 1]" in result["content"]


async def test_a_long_document_is_truncated_and_says_so(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    """A 200-page PDF must not push the conversation out of the context."""
    await _document(
        db_session,
        seed_user,
        "Long.pdf",
        [_chunk(i, "x" * 2000) for i in range(20)],
    )
    result = await doc_read.execute(
        ToolContext(session=db_session, user_id=seed_user), {"ref": "Long"}
    )
    assert result["truncated"] is True
    assert len(result["content"]) <= doc_read._MAX_CHARS + 200


async def test_an_empty_ref_is_rejected(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    ctx = ToolContext(session=db_session, user_id=seed_user)
    try:
        await doc_read.execute(ctx, {"ref": "   "})
    except ValueError:
        return
    raise AssertionError("an empty ref must raise rather than read something")
