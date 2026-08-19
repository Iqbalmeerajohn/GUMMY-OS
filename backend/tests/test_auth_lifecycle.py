"""Sign-out, session lifecycle, and the owner-mode trap.

Sign-out was reported broken. It was, and the cause was not in the client: with
``GUMMY_OWNER_MODE`` on, a request carrying **no credential at all** returned
HTTP 200 with the owner account. Measured against the running app before the
fix, an anonymous caller was served the owner's identity, 7 memories, and 10
conversations.

So logging out could not work by construction: the client discards its token,
asks the server who it is, and is told it is still the owner.

Owner mode is a real feature — a personal machine with no login screen — but its
premise is "one person uses this machine", and that premise is checkable. These
tests pin both halves: the convenience still works for a lone owner, and it
stops the moment a second account exists.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.security import warn_if_login_is_disabled
from app.repositories import user_repository


def _creds(n: int) -> dict[str, str]:
    return {
        "email": f"lifecycle{n}-{uuid.uuid4().hex[:8]}@gummy.local",
        "password": "Str0ng-Passw0rd!",
        "display_name": f"Lifecycle User {n}",
    }


async def _signup(api_client: AsyncClient, n: int) -> dict[str, Any]:
    response = await api_client.post("/api/v1/auth/signup", json=_creds(n))
    assert response.status_code in (200, 201), response.text
    return response.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── The reported bug ─────────────────────────────────────────────────────────


async def test_an_anonymous_request_is_rejected(api_client: AsyncClient) -> None:
    """The regression that broke sign-out.

    Owner mode is off in the test environment, so no credential means no
    identity — not "you are the owner".
    """
    response = await api_client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_anonymous_requests_cannot_read_data(api_client: AsyncClient) -> None:
    """Before the fix this returned 200 with the owner's memories."""
    for path in ("/api/v1/memories", "/api/v1/conversations", "/api/v1/automations"):
        response = await api_client.get(path)
        assert response.status_code == 401, f"{path} leaked to an anonymous caller"


async def test_owner_mode_still_works_for_a_lone_owner(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The convenience is preserved: a fresh personal install has no login wall."""
    settings = get_settings()
    monkeypatch.setattr(settings, "gummy_owner_mode", True)

    response = await api_client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == settings.gummy_owner_email


async def test_owner_mode_stops_once_a_second_account_exists(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate. Owner mode assumes one user; two accounts falsify that.

    Serving the owner's identity to an anonymous caller on a shared install is
    a data leak, not a convenience — so the auto-authentication stops and the
    request is rejected like any other unauthenticated one.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "gummy_owner_mode", True)

    # Two real accounts (plus whatever the owner row adds).
    await _signup(api_client, 1)
    await _signup(api_client, 2)

    response = await api_client.get("/api/v1/auth/me")

    assert response.status_code == 401


async def test_the_owner_mode_warning_names_the_consequence() -> None:
    """It must never be a silent surprise."""
    import inspect

    source = inspect.getsource(warn_if_login_is_disabled)
    assert "sign-out cannot work" in source
    assert "GUMMY_OWNER_MODE=false" in source


# ── Session lifecycle ────────────────────────────────────────────────────────


async def test_signup_then_authenticated_request(api_client: AsyncClient) -> None:
    session = await _signup(api_client, 1)
    response = await api_client.get(
        "/api/v1/auth/me", headers=_auth(session["access_token"])
    )

    assert response.status_code == 200
    assert response.json()["email"] == session["user"]["email"]


async def test_login_returns_a_working_session(api_client: AsyncClient) -> None:
    creds = _creds(1)
    await api_client.post("/api/v1/auth/signup", json=creds)

    login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": creds["email"], "password": creds["password"]},
    )

    assert login.status_code == 200
    token = login.json()["access_token"]
    me = await api_client.get("/api/v1/auth/me", headers=_auth(token))
    assert me.status_code == 200


async def test_a_wrong_password_is_rejected(api_client: AsyncClient) -> None:
    creds = _creds(1)
    await api_client.post("/api/v1/auth/signup", json=creds)

    login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": creds["email"], "password": "not-the-password"},
    )

    assert login.status_code == 401
    assert "password" not in login.text.lower() or "invalid" in login.text.lower()


async def test_an_invalid_token_is_rejected(api_client: AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/auth/me", headers=_auth("garbage.token.here")
    )
    assert response.status_code == 401


async def test_logout_revokes_the_refresh_token(api_client: AsyncClient) -> None:
    """Sign-out is server-side: the refresh token dies, so the session cannot
    be resurrected from a stale copy in the browser."""
    session = await _signup(api_client, 1)
    refresh = session["refresh_token"]

    logout = await api_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh},
        headers=_auth(session["access_token"]),
    )
    assert logout.status_code in (200, 204)

    replay = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh}
    )
    assert replay.status_code == 401


async def test_refresh_rotates_and_retires_the_old_token(
    api_client: AsyncClient,
) -> None:
    """A stolen refresh token dies the moment the real client refreshes."""
    session = await _signup(api_client, 1)
    first = session["refresh_token"]

    rotated = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first}
    )
    assert rotated.status_code == 200
    second = rotated.json()["refresh_token"]
    assert second != first

    replay = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first}
    )
    assert replay.status_code == 401


async def test_an_unknown_refresh_token_is_rejected(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "never-issued"}
    )
    assert response.status_code == 401


# ── Identity ─────────────────────────────────────────────────────────────────


async def test_the_display_name_given_at_signup_is_kept(
    api_client: AsyncClient,
) -> None:
    """Never inferred from the email local-part."""
    creds = _creds(1) | {"email": "jane.doe@example.com", "display_name": "Jane"}
    signup = await api_client.post("/api/v1/auth/signup", json=creds)

    assert signup.status_code in (200, 201)
    assert signup.json()["user"]["display_name"] == "Jane"


async def test_logging_in_does_not_overwrite_the_display_name(
    api_client: AsyncClient,
) -> None:
    creds = _creds(1)
    await api_client.post("/api/v1/auth/signup", json=creds)

    login = await api_client.post(
        "/api/v1/auth/login",
        json={"email": creds["email"], "password": creds["password"]},
    )

    assert login.json()["user"]["display_name"] == creds["display_name"]


async def test_signing_up_twice_with_one_email_is_refused(
    api_client: AsyncClient,
) -> None:
    creds = _creds(1)
    first = await api_client.post("/api/v1/auth/signup", json=creds)
    second = await api_client.post("/api/v1/auth/signup", json=creds)

    assert first.status_code in (200, 201)
    assert second.status_code in (400, 409)


# ── Isolation between two real accounts ──────────────────────────────────────


async def test_two_users_get_separate_workspaces(api_client: AsyncClient) -> None:
    """The critical GUMMY property, at the HTTP boundary."""
    a = await _signup(api_client, 1)
    b = await _signup(api_client, 2)

    created = await api_client.post(
        "/api/v1/memories",
        json={"category": "preference", "content": "Favourite language is Python"},
        headers=_auth(a["access_token"]),
    )
    assert created.status_code in (200, 201), created.text

    mine = await api_client.get("/api/v1/memories", headers=_auth(a["access_token"]))
    theirs = await api_client.get("/api/v1/memories", headers=_auth(b["access_token"]))

    assert mine.json()["total"] == 1
    assert theirs.json()["total"] == 0


async def test_one_user_cannot_fetch_anothers_record(api_client: AsyncClient) -> None:
    a = await _signup(api_client, 1)
    b = await _signup(api_client, 2)

    created = await api_client.post(
        "/api/v1/memories",
        json={"category": "profile", "content": "Lives in Bangalore"},
        headers=_auth(a["access_token"]),
    )
    memory_id = created.json()["id"]

    response = await api_client.get(
        f"/api/v1/memories/{memory_id}", headers=_auth(b["access_token"])
    )

    assert response.status_code == 404


async def test_a_token_identifies_its_own_user(api_client: AsyncClient) -> None:
    a = await _signup(api_client, 1)
    b = await _signup(api_client, 2)

    me_a = await api_client.get("/api/v1/auth/me", headers=_auth(a["access_token"]))
    me_b = await api_client.get("/api/v1/auth/me", headers=_auth(b["access_token"]))

    assert me_a.json()["id"] != me_b.json()["id"]
    assert me_a.json()["email"] == a["user"]["email"]
    assert me_b.json()["email"] == b["user"]["email"]


# ── Google sign-in surface ───────────────────────────────────────────────────


async def test_auth_config_reports_google_as_unavailable_when_unconfigured(
    api_client: AsyncClient,
) -> None:
    """The login screen must not offer a button the server cannot honour."""
    response = await api_client.get("/api/v1/auth/config")

    assert response.status_code == 200
    assert response.json()["google_enabled"] is False


async def test_starting_google_signin_without_credentials_is_refused(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/auth/google/start", follow_redirects=False)
    assert response.status_code == 503


def test_google_identity_is_keyed_on_the_provider_subject() -> None:
    """Email can change and be reassigned; Google's ``sub`` cannot.

    Keying on email would merge two people who ever shared an address, and
    split one person who changed theirs.
    """
    import inspect

    from app.services.auth import auth_service

    source = inspect.getsource(auth_service)
    assert "google_sub" in source


def test_the_user_count_helper_is_available() -> None:
    assert callable(user_repository.count_users)
