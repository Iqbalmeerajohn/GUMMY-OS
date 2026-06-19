"""Authentication primitives: JWT verification and the current-user model.

Verifies Supabase-issued access tokens **locally** (no per-request call to
Supabase). Both signing schemes are supported, selected by the token's own
``alg`` header (constrained to the ``SUPABASE_JWT_ALGORITHMS`` allowlist):

* **HS256** (symmetric) — verified with the shared ``SUPABASE_JWT_SECRET``.
* **ES256 / RS256 / EdDSA** (asymmetric) — verified with the project's public key,
  fetched and cached from Supabase's JWKS endpoint (``SUPABASE_URL`` +
  ``/auth/v1/.well-known/jwks.json``). This is what Supabase issues after the
  "JWT Signing Keys" migration (current key ECC P-256 → ``ES256``).

Routing the key material by ``alg`` (secret for HS*, public key for everything
else) keeps the two schemes isolated, so there is no algorithm-confusion risk.
All failures map to ``AppError`` with HTTP 401 and a stable error code.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError

from app.core.config import Settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

# Small leeway (seconds) to tolerate minor client/server clock skew on exp/iat.
_JWT_LEEWAY_SECONDS = 30

# Cached JWKS clients keyed by endpoint URL. PyJWKClient caches the fetched key
# set, so the network round-trip happens once (then on key rotation), not per
# request.
_jwk_clients: dict[str, PyJWKClient] = {}


def _get_jwk_client(jwks_url: str) -> PyJWKClient:
    client = _jwk_clients.get(jwks_url)
    if client is None:
        client = PyJWKClient(jwks_url, cache_keys=True)
        _jwk_clients[jwks_url] = client
    return client


@dataclass(frozen=True)
class TokenClaims:
    """The verified, parsed claims we rely on from a Supabase access token."""

    sub: uuid.UUID
    email: str | None
    raw: dict[str, object]
    name: str | None = None


def _extract_name(payload: dict[str, object]) -> str | None:
    """Best-effort display name from Supabase claims (signup user_metadata).

    Supabase embeds ``user_metadata`` in the verified access token, so the name
    the user provided at signup is available WITHOUT any extra DB/Supabase call.
    Tries the common keys in order; returns ``None`` when none are present.
    """
    candidates: list[object] = []
    meta = payload.get("user_metadata")
    if isinstance(meta, dict):
        candidates += [meta.get("full_name"), meta.get("name"), meta.get("first_name")]
    candidates += [payload.get("name")]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated tenant for a request."""

    id: uuid.UUID
    email: str | None
    display_name: str | None = None


def _unauthorized(code: str, message: str) -> AppError:
    return AppError(message, code=code, status_code=401)


def _resolve_key(token: str, alg: str, settings: Settings) -> Any:
    """Pick the verification key for the token's algorithm.

    HS* → the shared ``SUPABASE_JWT_SECRET``; asymmetric (ES*/RS*/PS*/EdDSA) →
    the project's public key from Supabase's JWKS endpoint. Raises
    ``AppError(503)`` when the required config for that scheme is missing.
    """
    if alg.startswith("HS"):
        secret = settings.supabase_jwt_secret
        if not secret:
            raise AppError(
                "Auth is enabled but SUPABASE_JWT_SECRET is not configured.",
                code="auth_misconfigured",
                status_code=503,
            )
        return secret

    jwks_url = settings.supabase_jwks_url
    if not jwks_url:
        raise AppError(
            "Auth is enabled but SUPABASE_URL is not configured for JWKS "
            "(asymmetric) token verification.",
            code="auth_misconfigured",
            status_code=503,
        )
    try:
        return _get_jwk_client(jwks_url).get_signing_key_from_jwt(token).key
    except PyJWKClientError as exc:
        logger.warning("JWKS signing-key lookup failed: %s", exc)
        raise _unauthorized("invalid_token", "The access token is invalid.") from exc


def verify_access_token(token: str, settings: Settings) -> TokenClaims:
    """Verify a Supabase JWT (signature, exp, audience) and return its claims.

    Supports both HS256 (shared secret) and asymmetric ES256/RS256/EdDSA (JWKS
    public key), chosen by the token's ``alg`` header within the configured
    allowlist. Raises ``AppError(401)`` on any verification failure, or
    ``AppError(503)`` if the server is missing the config for that scheme.
    """
    try:
        alg = jwt.get_unverified_header(token).get("alg", "")
    except jwt.InvalidTokenError as exc:
        logger.warning("JWT header could not be parsed: %s", exc)
        raise _unauthorized("invalid_token", "The access token is invalid.") from exc

    allowed = settings.jwt_algorithms
    if alg not in allowed:
        logger.warning(
            "JWT alg %r is not in the allowed algorithms %s "
            "(set SUPABASE_JWT_ALGORITHMS to match the project's signing key).",
            alg,
            allowed,
        )
        raise _unauthorized("invalid_token", "The access token is invalid.")

    key = _resolve_key(token, alg, settings)

    try:
        payload: dict[str, object] = jwt.decode(
            token,
            key=key,
            algorithms=[alg],
            audience=settings.supabase_jwt_aud,
            leeway=_JWT_LEEWAY_SECONDS,
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("token_expired", "The access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        # Covers bad signature, wrong audience, malformed token, missing claims.
        logger.warning("JWT verification failed (alg=%s): %s", alg, exc)
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
        name=_extract_name(payload),
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
