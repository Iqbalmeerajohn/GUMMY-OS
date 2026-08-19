"""Local auth over HTTP: sign-up, sign-in, rotation, revocation.

GUMMY is its own identity provider now, so these paths are the whole front door
— there is no hosted service left to fall back on if they regress.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import get_settings

_EMAIL = "owner@local.test"
_PASSWORD = "correct-horse-battery"


async def _signup(client: AsyncClient, **overrides: str) -> dict:
    body = {"email": _EMAIL, "password": _PASSWORD, "display_name": "Owner"}
    body.update(overrides)
    response = await client.post("/api/v1/auth/signup", json=body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_signup_returns_a_usable_session(api_client: AsyncClient) -> None:
    session = await _signup(api_client)
    assert session["access_token"]
    assert session["refresh_token"]
    assert session["user"]["email"] == _EMAIL

    me = await api_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == _EMAIL


@pytest.mark.asyncio
async def test_duplicate_email_is_rejected(api_client: AsyncClient) -> None:
    await _signup(api_client)
    again = await api_client.post(
        "/api/v1/auth/signup", json={"email": _EMAIL, "password": _PASSWORD}
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_login_requires_the_right_password(api_client: AsyncClient) -> None:
    await _signup(api_client)

    wrong = await api_client.post(
        "/api/v1/auth/login", json={"email": _EMAIL, "password": "not-it"}
    )
    assert wrong.status_code == 401

    right = await api_client.post(
        "/api/v1/auth/login", json={"email": _EMAIL, "password": _PASSWORD}
    )
    assert right.status_code == 200
    assert right.json()["access_token"]


@pytest.mark.asyncio
async def test_unknown_account_fails_like_a_wrong_password(
    api_client: AsyncClient,
) -> None:
    """Same status either way: the response must not enumerate accounts."""
    response = await api_client.post(
        "/api/v1/auth/login", json={"email": "nobody@local.test", "password": _PASSWORD}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_and_retires_the_old_token(
    api_client: AsyncClient,
) -> None:
    session = await _signup(api_client)
    original = session["refresh_token"]

    rotated = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original}
    )
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != original

    # A stolen copy of the old token is worthless the moment it is rotated.
    replay = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original}
    )
    assert replay.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_the_refresh_token(api_client: AsyncClient) -> None:
    session = await _signup(api_client)
    token = session["refresh_token"]

    out = await api_client.post("/api/v1/auth/logout", json={"refresh_token": token})
    assert out.status_code == 204

    after = await api_client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert after.status_code == 401

    # Idempotent, and it never reveals whether the token existed.
    again = await api_client.post("/api/v1/auth/logout", json={"refresh_token": token})
    assert again.status_code == 204


@pytest.mark.asyncio
async def test_config_reports_available_sign_in_methods(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Forced absent, not assumed absent: this used to read the developer's real
    # .env, so the result depended on who ran it rather than on the code.
    settings = get_settings()
    monkeypatch.setattr(settings, "google_client_id", None)
    monkeypatch.setattr(settings, "google_client_secret", None)

    response = await client.get("/api/v1/auth/config")

    assert response.status_code == 200
    body = response.json()
    assert {"google_enabled", "owner_mode"} <= set(body)
    assert body["google_enabled"] is False
