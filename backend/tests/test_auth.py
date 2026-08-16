"""Auth unit tests: JWT verification + the production safety guard.

Hermetic — tokens are minted locally with PyJWT against the test secret, exactly
as ``token_service`` mints them at runtime; no network, no database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.security import assert_auth_safe, verify_access_token
from app.services.auth.token_service import TOKEN_AUDIENCE

_SECRET = "test-local-jwt-secret"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "gummy_jwt_secret": _SECRET,
        # assert_auth_safe refuses to start in production with owner mode on, so
        # without this every production-mode case here would fail on owner mode
        # rather than on what it means to test.
        "gummy_owner_mode": False,
        **overrides,
    }
    return Settings().model_copy(update=base)


def _token(
    *,
    secret: str = _SECRET,
    sub: str | None = None,
    aud: str = TOKEN_AUDIENCE,
    email: str | None = "user@example.com",
    expires_in: int = 3600,
    algorithm: str = "HS256",
) -> str:
    sub = sub or str(uuid.uuid4())
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": sub,
        "aud": aud,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    if email is not None:
        payload["email"] = email
    return jwt.encode(payload, secret, algorithm=algorithm)


def test_valid_token_returns_claims() -> None:
    uid = uuid.uuid4()
    claims = verify_access_token(_token(sub=str(uid), email="a@b.com"), _settings())
    assert claims.sub == uid
    assert claims.email == "a@b.com"


def test_token_without_email_yields_none() -> None:
    claims = verify_access_token(_token(email=None), _settings())
    assert claims.email is None


def test_display_name_comes_from_the_token() -> None:
    """The name rides in the token, so no DB read is needed to greet the user."""
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": TOKEN_AUDIENCE,
            "exp": now + timedelta(hours=1),
            "user_metadata": {"full_name": "Iqbal"},
        },
        _SECRET,
        algorithm="HS256",
    )
    assert verify_access_token(token, _settings()).name == "Iqbal"


def test_expired_token_raises_401() -> None:
    # Well beyond the 30s clock-skew leeway.
    with pytest.raises(AppError) as exc:
        verify_access_token(_token(expires_in=-300), _settings())
    assert exc.value.status_code == 401
    assert exc.value.code == "token_expired"


def test_bad_signature_raises_401() -> None:
    with pytest.raises(AppError) as exc:
        verify_access_token(_token(secret="wrong-secret"), _settings())
    assert exc.value.status_code == 401
    assert exc.value.code == "invalid_token"


def test_foreign_audience_raises_401() -> None:
    """A token signed for another product must not authenticate here."""
    with pytest.raises(AppError) as exc:
        verify_access_token(_token(aud="authenticated"), _settings())
    assert exc.value.code == "invalid_token"


def test_unsigned_token_raises_401() -> None:
    """`alg: none` is the classic forgery; only HS256 is accepted."""
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "aud": TOKEN_AUDIENCE,
            "exp": now + timedelta(hours=1),
        },
        key="",
        algorithm="none",
    )
    with pytest.raises(AppError) as exc:
        verify_access_token(token, _settings())
    assert exc.value.code == "invalid_token"


def test_malformed_token_raises_401() -> None:
    with pytest.raises(AppError) as exc:
        verify_access_token("not-a-jwt", _settings())
    assert exc.value.code == "invalid_token"


def test_non_uuid_subject_raises_401() -> None:
    with pytest.raises(AppError) as exc:
        verify_access_token(_token(sub="not-a-uuid"), _settings())
    assert exc.value.code == "invalid_token"


def test_missing_secret_raises_503() -> None:
    with pytest.raises(AppError) as exc:
        verify_access_token(_token(), _settings(gummy_jwt_secret=None, secret_key=""))
    assert exc.value.status_code == 503
    assert exc.value.code == "auth_misconfigured"


def test_assert_auth_safe_blocks_bypass_in_production() -> None:
    with pytest.raises(RuntimeError):
        assert_auth_safe(_settings(app_env="production", auth_dev_bypass=True))


def test_assert_auth_safe_allows_dev_bypass() -> None:
    assert_auth_safe(_settings(app_env="development", auth_dev_bypass=True))


def test_assert_auth_safe_allows_production_without_bypass() -> None:
    assert_auth_safe(_settings(app_env="production", auth_dev_bypass=False))
