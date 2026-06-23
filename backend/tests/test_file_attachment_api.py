"""M6.5 API: chat attachments end-to-end through the turn endpoint.

Confirms attached files flow into a turn, and that a foreign/missing attachment
id is rejected with 404 (tenant-isolation safety contract). pgvector memory
search is monkeypatched (unavailable on the SQLite test DB).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.memory import Memory
from app.services.files import file_service
from app.services.files.storage.local_provider import LocalFileStorage

_TENANT = uuid.uuid4()


def _q(user: uuid.UUID = _TENANT) -> dict[str, str]:
    return {"user_id": str(user)}


@pytest.fixture(autouse=True)
def _wiring(tmp_path, monkeypatch) -> None:
    storage = LocalFileStorage(str(tmp_path / "files"))
    monkeypatch.setattr(file_service, "get_file_storage", lambda: storage)

    async def _empty(*args, **kwargs) -> list[tuple[Memory, float]]:
        return []

    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories", _empty
    )


async def _new_conversation(api_client: AsyncClient) -> str:
    res = await api_client.post(
        "/api/v1/conversations", params=_q(), json={"agent_context": "general"}
    )
    return res.json()["id"]


async def test_turn_with_attachment_succeeds(api_client: AsyncClient) -> None:
    upload = await api_client.post(
        "/api/v1/files/upload",
        params=_q(),
        files={
            "file": (
                "report.txt",
                b"Quarterly revenue grew thirty percent in Q3.",
                "text/plain",
            )
        },
    )
    file_id = upload.json()["id"]
    conversation_id = await _new_conversation(api_client)

    turn = await api_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        params=_q(),
        json={
            "message": "Summarize this document",
            "attachment_file_ids": [file_id],
        },
    )
    assert turn.status_code == 201, turn.text
    assert turn.json()["reply"]


async def test_turn_with_foreign_attachment_404(api_client: AsyncClient) -> None:
    conversation_id = await _new_conversation(api_client)
    turn = await api_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        params=_q(),
        json={
            "message": "Summarize this",
            "attachment_file_ids": [str(uuid.uuid4())],  # not the tenant's file
        },
    )
    assert turn.status_code == 404


async def test_turn_without_attachment_still_works(
    api_client: AsyncClient,
) -> None:
    conversation_id = await _new_conversation(api_client)
    turn = await api_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        params=_q(),
        json={"message": "Hello"},
    )
    assert turn.status_code == 201
