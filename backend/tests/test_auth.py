"""Auth unit tests: JWT verification + the production safety guard.

Hermetic — tokens are minted locally with PyJWT against a test secret; no network.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.security import assert_auth_safe, verify_access_token

_SECRET = "test-jwt-secret"


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "supabase_jwt_secret": _SECRET,
        "supabase_jwt_aud": "authenticated",
        "supabase_jwt_algorithms": "HS256",
        **overrides,
    }
    return Settings().model_copy(update=base)


def _token(
    *,
    secret: str = _SECRET,
    sub: str | None = None,
    aud: str = "authenticated",
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


def test_wrong_audience_raises_401() -> None:
    with pytest.raises(AppError) as exc:
        verify_access_token(_token(aud="some-other-aud"), _settings())
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
        verify_access_token(_token(), _settings(supabase_jwt_secret=None))
    assert exc.value.status_code == 503
    assert exc.value.code == "auth_misconfigured"


def test_assert_auth_safe_blocks_bypass_in_production() -> None:
    with pytest.raises(RuntimeError):
        assert_auth_safe(_settings(app_env="production", auth_dev_bypass=True))


def test_assert_auth_safe_allows_dev_bypass() -> None:
    assert_auth_safe(_settings(app_env="development", auth_dev_bypass=True))


def test_assert_auth_safe_allows_production_without_bypass() -> None:
    assert_auth_safe(_settings(app_env="production", auth_dev_bypass=False))
