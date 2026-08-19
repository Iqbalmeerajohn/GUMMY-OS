"""Password recovery: the token is a bearer credential for the account.

The login screen has linked to ``/forgot-password`` since local auth landed,
but nothing served it — no page, no endpoint, no table. Both halves 404'd.

A reset token is, for its lifetime, a password. So these tests are mostly about
the ways it must stop working: once used, once expired, once superseded, and
against any account other than the one it was minted for. The single-use
property in particular is the difference between a link in an inbox being a
momentary risk and a permanent one.

The other half is what the endpoint must *not* say. Answering differently for a
known and an unknown address turns forgot-password into a free
account-enumeration oracle, so the generic response is asserted to be
byte-identical across both cases rather than merely "similar".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.auth import mailer, reset_service

OLD_PASSWORD = "Str0ng-Passw0rd!"
NEW_PASSWORD = "Even-Str0nger-Passw0rd!"


def _creds(tag: str) -> dict[str, str]:
    return {
        "email": f"reset-{tag}-{uuid.uuid4().hex[:8]}@gummy.local",
        "password": OLD_PASSWORD,
        "display_name": f"Reset User {tag}",
    }


async def _signup(api_client: AsyncClient, tag: str) -> dict[str, Any]:
    creds = _creds(tag)
    response = await api_client.post("/api/v1/auth/signup", json=creds)
    assert response.status_code in (200, 201), response.text
    return {**response.json(), "email": creds["email"]}


async def _forgot(api_client: AsyncClient, email: str) -> Any:
    return await api_client.post("/api/v1/auth/forgot-password", json={"email": email})


async def _reset(api_client: AsyncClient, token: str, password: str) -> Any:
    return await api_client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": password},
    )


async def _login(api_client: AsyncClient, email: str, password: str) -> Any:
    return await api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )


def _capture_token(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Intercept the delivered link and pull the raw token out of it.

    This is the only place the raw token is observable — which is the point of
    the design, and the reason the test has to reach for the mail layer rather
    than reading it out of the database.
    """
    sent: list[str] = []

    def _fake_send(message: mailer.Message, *, settings: Any) -> None:
        for word in message.body.split():
            if "token=" in word:
                sent.append(word.split("token=", 1)[1])

    monkeypatch.setattr(mailer, "send", _fake_send)
    return sent


# ── 1–3. The endpoint must not reveal whether an account exists ──────────────


async def test_forgot_password_succeeds_for_an_existing_account(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _capture_token(monkeypatch)
    account = await _signup(api_client, "existing")

    response = await _forgot(api_client, account["email"])

    assert response.status_code == 200, response.text
    assert response.json()["message"] == reset_service.GENERIC_RESET_RESPONSE


async def test_forgot_password_succeeds_for_a_nonexistent_account(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _capture_token(monkeypatch)

    response = await _forgot(api_client, "no-such-person@gummy.local")

    assert response.status_code == 200, response.text
    assert response.json()["message"] == reset_service.GENERIC_RESET_RESPONSE


async def test_both_cases_return_a_byte_identical_response(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The anti-enumeration property, asserted as equality rather than vibes."""
    _capture_token(monkeypatch)
    account = await _signup(api_client, "identical")

    known = await _forgot(api_client, account["email"])
    unknown = await _forgot(api_client, "definitely-not-a-user@gummy.local")

    assert known.status_code == unknown.status_code
    assert known.json() == unknown.json()


# ── 4–5. The token is created, and never stored in the clear ────────────────


async def test_a_reset_token_is_created(
    api_client: AsyncClient,
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture_token(monkeypatch)
    account = await _signup(api_client, "created")

    await _forgot(api_client, account["email"])

    assert len(sent) == 1, "exactly one reset link should have been delivered"
    async with sessionmaker_fixture() as session:
        rows = (await session.scalars(select(PasswordResetToken))).all()
    assert len(rows) == 1
    assert rows[0].used_at is None


async def test_the_raw_token_is_never_stored(
    api_client: AsyncClient,
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dump of this table must not yield a working reset link."""
    sent = _capture_token(monkeypatch)
    account = await _signup(api_client, "hashed")

    await _forgot(api_client, account["email"])
    raw = sent[0]

    async with sessionmaker_fixture() as session:
        row = (await session.scalars(select(PasswordResetToken))).one()

    assert row.token_hash != raw
    assert raw not in row.token_hash
    assert row.token_hash == reset_service.hash_reset_token(raw)
    assert len(row.token_hash) == 64  # sha256 hex


# ── 6–12. Redemption, and every way it must fail ────────────────────────────


async def test_a_valid_token_resets_the_password(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _capture_token(monkeypatch)
    account = await _signup(api_client, "valid")
    await _forgot(api_client, account["email"])

    response = await _reset(api_client, sent[0], NEW_PASSWORD)

    assert response.status_code == 200, response.text


async def test_an_unknown_token_is_rejected(api_client: AsyncClient) -> None:
    response = await _reset(api_client, "not-a-real-token", NEW_PASSWORD)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_reset_token"


async def test_an_expired_token_is_rejected(
    api_client: AsyncClient,
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture_token(monkeypatch)
    account = await _signup(api_client, "expired")
    await _forgot(api_client, account["email"])

    async with sessionmaker_fixture() as session:
        row = (await session.scalars(select(PasswordResetToken))).one()
        row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await session.commit()

    response = await _reset(api_client, sent[0], NEW_PASSWORD)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_reset_token"


async def test_a_used_token_is_rejected_and_cannot_be_reused(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Single-use is what bounds the damage of a link sitting in an inbox."""
    sent = _capture_token(monkeypatch)
    account = await _signup(api_client, "reuse")
    await _forgot(api_client, account["email"])
    token = sent[0]

    first = await _reset(api_client, token, NEW_PASSWORD)
    assert first.status_code == 200, first.text

    second = await _reset(api_client, token, "Third-Passw0rd-Attempt!")
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "invalid_reset_token"


async def test_the_old_password_stops_working_and_the_new_one_starts(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _capture_token(monkeypatch)
    account = await _signup(api_client, "swap")
    await _forgot(api_client, account["email"])
    await _reset(api_client, sent[0], NEW_PASSWORD)

    old = await _login(api_client, account["email"], OLD_PASSWORD)
    assert old.status_code == 401

    new = await _login(api_client, account["email"], NEW_PASSWORD)
    assert new.status_code == 200, new.text


async def test_requesting_a_second_link_invalidates_the_first(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise every "resend" leaves another live credential in an inbox."""
    sent = _capture_token(monkeypatch)
    account = await _signup(api_client, "supersede")

    await _forgot(api_client, account["email"])
    await _forgot(api_client, account["email"])
    first, second = sent[0], sent[1]

    stale = await _reset(api_client, first, NEW_PASSWORD)
    assert stale.status_code == 400

    fresh = await _reset(api_client, second, NEW_PASSWORD)
    assert fresh.status_code == 200, fresh.text


# ── 13. Sessions die with the old password ──────────────────────────────────


async def test_existing_sessions_are_revoked_by_a_reset(
    api_client: AsyncClient,
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reset the user did not initiate is an intrusion; the intruder's
    session must not outlive the password that opened it."""
    sent = _capture_token(monkeypatch)
    account = await _signup(api_client, "sessions")
    refresh_token = account["refresh_token"]

    still_valid = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert still_valid.status_code == 200, "sanity: the session works before reset"
    rotated = still_valid.json()["refresh_token"]

    await _forgot(api_client, account["email"])
    await _reset(api_client, sent[0], NEW_PASSWORD)

    dead = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated}
    )
    assert dead.status_code == 401

    async with sessionmaker_fixture() as session:
        rows = (await session.scalars(select(RefreshToken))).all()
    assert all(r.revoked_at is not None for r in rows)


# ── 14. Password policy is shared, not re-specified ─────────────────────────


@pytest.mark.parametrize("weak", ["short", "1234567", ""])
async def test_a_weak_password_is_rejected(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch, weak: str
) -> None:
    sent = _capture_token(monkeypatch)
    account = await _signup(api_client, "weak")
    await _forgot(api_client, account["email"])

    response = await _reset(api_client, sent[0], weak)

    assert response.status_code == 422


async def test_reset_enforces_exactly_the_signup_password_policy() -> None:
    """One definition, not two.

    A reset flow that re-specifies the bounds is how an app ends up accepting a
    weaker password on recovery than it ever allowed at sign-up.
    """
    from app.schemas.auth import ResetPasswordRequest, SignUpRequest

    def _bounds(model: type, field: str) -> tuple[int | None, int | None]:
        meta = model.model_fields[field].metadata
        lo = next((m.min_length for m in meta if hasattr(m, "min_length")), None)
        hi = next((m.max_length for m in meta if hasattr(m, "max_length")), None)
        return lo, hi

    assert _bounds(ResetPasswordRequest, "new_password") == _bounds(
        SignUpRequest, "password"
    )


async def test_a_rejected_weak_password_does_not_spend_the_token(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """422 is the user mistyping, not an attack. Burning their only link over
    it would strand them."""
    sent = _capture_token(monkeypatch)
    account = await _signup(api_client, "notspent")
    await _forgot(api_client, account["email"])

    rejected = await _reset(api_client, sent[0], "short")
    assert rejected.status_code == 422

    accepted = await _reset(api_client, sent[0], NEW_PASSWORD)
    assert accepted.status_code == 200, accepted.text


# ── 16–17. Cross-user isolation ─────────────────────────────────────────────


async def test_a_token_only_resets_the_account_it_was_minted_for(
    api_client: AsyncClient,
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User A's link must be inert against User B, and B's password untouched."""
    sent = _capture_token(monkeypatch)
    user_a = await _signup(api_client, "aaa")
    user_b = await _signup(api_client, "bbb")

    await _forgot(api_client, user_a["email"])
    token_a = sent[0]

    response = await _reset(api_client, token_a, NEW_PASSWORD)
    assert response.status_code == 200, response.text

    # B is untouched: original password still works, new one does not.
    assert (await _login(api_client, user_b["email"], OLD_PASSWORD)).status_code == 200
    assert (await _login(api_client, user_b["email"], NEW_PASSWORD)).status_code == 401

    # And the token was bound to A's row all along.
    async with sessionmaker_fixture() as session:
        row = (
            await session.scalars(
                select(PasswordResetToken).where(
                    PasswordResetToken.token_hash
                    == reset_service.hash_reset_token(token_a)
                )
            )
        ).one()
        a_id = uuid.UUID(user_a["user"]["id"])
    assert row.user_id == a_id


async def test_resetting_one_account_leaves_the_others_sessions_alive(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = _capture_token(monkeypatch)
    user_a = await _signup(api_client, "sess-a")
    user_b = await _signup(api_client, "sess-b")

    await _forgot(api_client, user_a["email"])
    await _reset(api_client, sent[0], NEW_PASSWORD)

    alive = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": user_b["refresh_token"]}
    )
    assert alive.status_code == 200, alive.text


# ── A Google-only account has no password to reset ──────────────────────────


async def test_a_google_only_account_gets_no_reset_token(
    api_client: AsyncClient,
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Minting one would silently convert it into a password account.

    The response stays generic, so this is invisible to the caller.
    """
    sent = _capture_token(monkeypatch)
    email = f"google-only-{uuid.uuid4().hex[:8]}@gummy.local"
    async with sessionmaker_fixture() as session:
        session.add(User(email=email, google_sub="sub-123", password_hash=None))
        await session.commit()

    response = await _forgot(api_client, email)

    assert response.status_code == 200
    assert response.json()["message"] == reset_service.GENERIC_RESET_RESPONSE
    assert sent == []
    async with sessionmaker_fixture() as session:
        assert (await session.scalars(select(PasswordResetToken))).all() == []


# ── 18–19. Delivery modes ───────────────────────────────────────────────────


def test_console_mode_logs_the_link_and_sends_nothing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_email_mode", "console")

    with caplog.at_level("INFO", logger="app.services.auth.mailer"):
        mailer.send(
            mailer.Message(to="a@b.c", subject="Reset", body="http://x/?token=abc"),
            settings=settings,
        )

    assert "GUMMY AUTH" in caplog.text
    assert "token=abc" in caplog.text
    assert settings.auth_email_console_mode is True


def test_smtp_mode_without_a_host_fails_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rather than silently falling back to console and looking like it worked."""
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_email_mode", "smtp")
    monkeypatch.setattr(settings, "smtp_host", None)

    with pytest.raises(mailer.MailDeliveryError):
        mailer.send(
            mailer.Message(to="a@b.c", subject="s", body="b"), settings=settings
        )


def test_a_failed_smtp_send_does_not_log_credentials(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Provider error strings sometimes echo the username back."""
    import smtplib

    settings = get_settings()
    monkeypatch.setattr(settings, "auth_email_mode", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_username", "user@example.com")
    monkeypatch.setattr(settings, "smtp_password", "hunter2-secret")

    def _boom(*args: Any, **kwargs: Any) -> None:
        raise smtplib.SMTPAuthenticationError(535, b"auth failed for user@example.com")

    monkeypatch.setattr(smtplib, "SMTP", _boom)

    with (
        caplog.at_level("ERROR", logger="app.services.auth.mailer"),
        pytest.raises(mailer.MailDeliveryError),
    ):
        mailer.send(
            mailer.Message(to="a@b.c", subject="s", body="b"), settings=settings
        )

    assert "hunter2-secret" not in caplog.text


def test_an_invalid_email_mode_is_rejected_at_config_time() -> None:
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(auth_email_mode="carrier-pigeon")


def test_the_reset_link_points_at_the_configured_frontend() -> None:
    settings = get_settings()

    link = reset_service._reset_link("abc123", settings=settings)

    assert link.startswith(settings.frontend_url.rstrip("/"))
    assert link.endswith("/reset-password?token=abc123")


# ── 20–24. The rest of auth still works ─────────────────────────────────────


async def test_signup_login_and_logout_still_work(api_client: AsyncClient) -> None:
    account = await _signup(api_client, "regression")

    login = await _login(api_client, account["email"], OLD_PASSWORD)
    assert login.status_code == 200, login.text

    logout = await api_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": login.json()["refresh_token"]},
    )
    assert logout.status_code == 204


async def test_anonymous_api_access_is_still_rejected(
    api_client: AsyncClient,
) -> None:
    assert (await api_client.get("/api/v1/auth/me")).status_code == 401


async def test_auth_config_reports_the_email_mode(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/auth/config")

    assert response.status_code == 200
    body = response.json()
    assert body["email_console_mode"] is True
    # Google's status is reported, not changed, by this milestone.
    assert body["google_enabled"] == get_settings().google_oauth_enabled


async def test_google_oauth_start_is_unaffected(api_client: AsyncClient) -> None:
    """No credentials are configured in the test environment, so the endpoint
    must still refuse cleanly rather than 500."""
    response = await api_client.get("/api/v1/auth/google/start", follow_redirects=False)

    assert response.status_code in (307, 503), response.text
