"""Files API tests (M6): upload, list, get, chunks, stats, delete, tenancy."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.services.files import file_service
from app.services.files.storage.local_provider import LocalFileStorage

_TENANT = uuid.uuid4()
_OTHER = uuid.uuid4()


def _q(user: uuid.UUID = _TENANT) -> dict[str, str]:
    return {"user_id": str(user)}


@pytest.fixture(autouse=True)
def _temp_storage(tmp_path, monkeypatch) -> None:
    """Redirect the upload/delete storage backend to a temp dir for each test."""
    storage = LocalFileStorage(str(tmp_path / "files"))
    monkeypatch.setattr(file_service, "get_file_storage", lambda: storage)


async def test_upload_and_get(api_client: AsyncClient) -> None:
    res = await api_client.post(
        "/api/v1/files/upload",
        params=_q(),
        files={"file": ("notes.txt", b"hello knowledge base", "text/plain")},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["original_filename"] == "notes.txt"
    assert body["upload_status"] == "uploaded"
    assert body["processing_status"] == "completed"
    assert body["chunk_count"] >= 1

    fetched = await api_client.get(f"/api/v1/files/{body['id']}", params=_q())
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


async def test_list_and_stats(api_client: AsyncClient) -> None:
    # Distinct content per file: identical bytes are now deduplicated by
    # checksum, so uploading the same text twice yields one file, not two.
    for name, body in (
        ("a.txt", b"alpha content here"),
        ("b.md", b"beta content here"),
    ):
        await api_client.post(
            "/api/v1/files/upload",
            params=_q(),
            files={"file": (name, body, "text/plain")},
        )
    listed = await api_client.get("/api/v1/files", params=_q())
    assert listed.status_code == 200
    assert listed.json()["total"] == 2

    stats = await api_client.get("/api/v1/files/stats", params=_q())
    assert stats.status_code == 200
    assert stats.json()["total"] == 2
    assert len(stats.json()["recent"]) == 2


async def test_list_chunks(api_client: AsyncClient) -> None:
    res = await api_client.post(
        "/api/v1/files/upload",
        params=_q(),
        files={"file": ("big.txt", ("word " * 800).encode(), "text/plain")},
    )
    file_id = res.json()["id"]
    chunks = await api_client.get(f"/api/v1/files/{file_id}/chunks", params=_q())
    assert chunks.status_code == 200
    payload = chunks.json()
    assert payload["total"] >= 1
    assert payload["items"][0]["chunk_index"] == 0
    assert "content" in payload["items"][0]


async def test_upload_unsupported_type_415(api_client: AsyncClient) -> None:
    res = await api_client.post(
        "/api/v1/files/upload",
        params=_q(),
        files={"file": ("img.png", b"\x89PNG\r\n", "image/png")},
    )
    assert res.status_code == 415


async def test_delete(api_client: AsyncClient) -> None:
    res = await api_client.post(
        "/api/v1/files/upload",
        params=_q(),
        files={"file": ("temp.txt", b"delete me", "text/plain")},
    )
    file_id = res.json()["id"]
    deleted = await api_client.delete(f"/api/v1/files/{file_id}", params=_q())
    assert deleted.status_code == 204
    gone = await api_client.get(f"/api/v1/files/{file_id}", params=_q())
    assert gone.status_code == 404


async def test_tenant_isolation(api_client: AsyncClient) -> None:
    res = await api_client.post(
        "/api/v1/files/upload",
        params=_q(_TENANT),
        files={"file": ("mine.txt", b"private data", "text/plain")},
    )
    file_id = res.json()["id"]
    # Another tenant cannot see it.
    other = await api_client.get(f"/api/v1/files/{file_id}", params=_q(_OTHER))
    assert other.status_code == 404
    listed = await api_client.get("/api/v1/files", params=_q(_OTHER))
    assert listed.json()["total"] == 0


async def test_get_missing_file_404(api_client: AsyncClient) -> None:
    res = await api_client.get(f"/api/v1/files/{uuid.uuid4()}", params=_q())
    assert res.status_code == 404
