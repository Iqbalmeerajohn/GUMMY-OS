"""Authentication primitives: JWT verification and the current-user model.

Verifies Supabase-issued access tokens **locally** (no per-request call to
Supabase). HS256 (symmetric, via ``SUPABASE_JWT_SECRET``) is implemented today; the
accepted-algorithm list is a config seam (``SUPABASE_JWT_ALGORITHMS``) so RS256/JWKS
can be added later without touching call sites. All failures map to ``AppError``
with HTTP 401 and a stable error code.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt

from app.core.config import Settings
from app.core.exceptions import AppError

# Small leeway (seconds) to tolerate minor client/server clock skew on exp/iat.
_JWT_LEEWAY_SECONDS = 30


@dataclass(frozen=True)
class TokenClaims:
    """The verified, parsed claims we rely on from a Supabase access token."""

    sub: uuid.UUID
    email: str | None
    raw: dict[str, object]


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated tenant for a request."""

    id: uuid.UUID
    email: str | None


def _unauthorized(code: str, message: str) -> AppError:
    return AppError(message, code=code, status_code=401)


def verify_access_token(token: str, settings: Settings) -> TokenClaims:
    """Verify a Supabase JWT (signature, exp, audience) and return its claims.

    Raises ``AppError(401)`` on any verification failure, or ``AppError(503)`` if
    the server is missing the signing secret (a misconfiguration, not a client
    error).
    """
    secret = settings.supabase_jwt_secret
    if not secret:
        raise AppError(
            "Auth is enabled but SUPABASE_JWT_SECRET is not configured.",
            code="auth_misconfigured",
            status_code=503,
        )

    try:
        payload: dict[str, object] = jwt.decode(
            token,
            key=secret,
            algorithms=settings.jwt_algorithms,
            audience=settings.supabase_jwt_aud,
            leeway=_JWT_LEEWAY_SECONDS,
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("token_expired", "The access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        # Covers bad signature, wrong audience, malformed token, missing claims.
        raise _unauthorized("invalid_token", "The access token is invalid.") from exc

    sub = payload.get("sub")
    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise _unauthorized(
            "invalid_token", "The access token has an invalid subject."
        ) from exc

    email = payload.get("email")
    return TokenClaims(
        sub=user_id,
        email=str(email) if isinstance(email, str) else None,
        raw=payload,
    )


def assert_auth_safe(settings: Settings) -> None:
    """Fail fast if an insecure auth configuration would reach production.

    The dev bypass (legacy ``user_id`` query param / fixed dev user) must never be
    enabled in production — it would disable authentication entirely.
    """
    if settings.is_production and settings.auth_dev_bypass:
        raise RuntimeError(
            "auth_dev_bypass must be disabled in production " "(AUTH_DEV_BYPASS=false)."
        )
