"""End-to-end auth tests over HTTP: bearer-token tenancy, rejection, override.

Tokens are minted locally (HS256, GUMMY_JWT_SECRET from conftest) — no network.
The token-path user upsert hits the same in-memory SQLite as the request session.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.services.auth.token_service import TOKEN_AUDIENCE

_SECRET = "test-local-jwt-secret"  # matches GUMMY_JWT_SECRET in conftest


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token(
    *,
    sub: str | None = None,
    aud: str = TOKEN_AUDIENCE,
    email: str | None = "user@example.com",
    expires_in: int = 3600,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": sub or str(uuid.uuid4()),
        "aud": aud,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    if email is not None:
        payload["email"] = email
    return jwt.encode(payload, _SECRET, algorithm="HS256")


async def test_token_auth_creates_user_and_scopes_memory(
    api_client: AsyncClient,
) -> None:
    sub = uuid.uuid4()
    resp = await api_client.post(
        "/api/v1/memories",
        headers=_bearer(_token(sub=str(sub), email="founder@example.com")),
        json={"category": "career", "content": "Targeting Qualcomm"},
    )
    assert resp.status_code == 201
    # Tenancy came from the JWT `sub` (no user_id query param was sent).
    assert resp.json()["user_id"] == str(sub)


async def test_token_scopes_listing(api_client: AsyncClient) -> None:
    token = _token(sub=str(uuid.uuid4()))
    await api_client.post(
        "/api/v1/memories",
        headers=_bearer(token),
        json={"category": "profile", "content": "Bangalore"},
    )
    resp = await api_client.get("/api/v1/memories", headers=_bearer(token))
    assert resp.status_code == 200
    assert resp.json()["total"] == 1


async def test_invalid_token_rejected(api_client: AsyncClient) -> None:
    resp = await api_client.get(
        "/api/v1/memories", headers=_bearer("garbage.token.value")
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_token"


async def test_expired_token_rejected(api_client: AsyncClient) -> None:
    resp = await api_client.get(
        "/api/v1/memories", headers=_bearer(_token(expires_in=-300))
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "token_expired"


async def test_missing_token_with_bypass_off_rejected(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "auth_dev_bypass", False)
    resp = await api_client.get("/api/v1/memories")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "missing_token"


async def test_token_overrides_legacy_user_id_param(
    api_client: AsyncClient,
) -> None:
    sub = uuid.uuid4()
    other = uuid.uuid4()
    resp = await api_client.post(
        "/api/v1/memories",
        params={"user_id": str(other)},  # legacy param present...
        headers=_bearer(_token(sub=str(sub))),  # ...but a valid token wins
        json={"category": "profile", "content": "Y"},
    )
    assert resp.status_code == 201
    assert resp.json()["user_id"] == str(sub)
