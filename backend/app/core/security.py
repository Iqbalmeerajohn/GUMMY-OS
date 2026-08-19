"""Authentication primitives: JWT verification and the current-user model.

GUMMY is its own identity provider: access tokens are HS256 JWTs minted by
``app.services.auth.token_service`` and verified here against the local secret.
Verification is self-contained — no database read, no network call — so
authentication stays off the request latency budget and sign-in keeps working
with the machine offline.

Exactly one issuer and one algorithm are accepted. That is the whole point: with
no second scheme there is no key routing, and therefore no algorithm-confusion
risk. All failures map to ``AppError`` with HTTP 401 and a stable error code.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import jwt

from app.core.config import Settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

# Small leeway (seconds) to tolerate minor client/server clock skew on exp/iat.
_JWT_LEEWAY_SECONDS = 30


@dataclass(frozen=True)
class TokenClaims:
    """The verified, parsed claims we rely on from an access token."""

    sub: uuid.UUID
    email: str | None
    raw: dict[str, object]
    name: str | None = None


def _extract_name(payload: dict[str, object]) -> str | None:
    """Best-effort display name from the token's ``user_metadata`` claim.

    The name given at signup rides in the token itself, so it is available
    without an extra database read on the request path. Tries the common keys in
    order; returns ``None`` when none are present.
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


def verify_access_token(token: str, settings: Settings) -> TokenClaims:
    """Verify a GUMMY-issued access token (HS256, local secret) and return its claims.

    Raises ``AppError(401)`` on any verification failure — bad signature, wrong
    audience, expiry, malformed token — or ``AppError(503)`` when the server has
    no signing secret configured.
    """
    from app.services.auth.token_service import ALGORITHM, TOKEN_AUDIENCE

    if not settings.local_auth_secret:
        raise AppError(
            "Auth is enabled but GUMMY_JWT_SECRET is not configured.",
            code="auth_misconfigured",
            status_code=503,
        )

    try:
        payload: dict[str, object] = jwt.decode(
            token,
            key=settings.local_auth_secret,
            algorithms=[ALGORITHM],
            audience=TOKEN_AUDIENCE,
            leeway=_JWT_LEEWAY_SECONDS,
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("token_expired", "The access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        logger.warning("GUMMY token verification failed: %s", exc)
        raise _unauthorized("invalid_token", "The access token is invalid.") from exc

    return _claims_from_payload(payload)


def _claims_from_payload(payload: dict[str, object]) -> TokenClaims:
    """Build ``TokenClaims`` from an already-verified payload."""
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


def warn_if_login_is_disabled(settings: Settings) -> None:
    """Log loudly when owner mode is on outside production.

    Owner mode and sign-out are mutually exclusive: if every request without a
    credential resolves to the owner, then discarding the token cannot log
    anyone out. That trade is fine for a personal machine with no login screen
    and surprising everywhere else, so it is stated at boot rather than
    discovered when sign-out appears broken.
    """
    if settings.gummy_owner_mode and not settings.is_production:
        logger.warning(
            "GUMMY_OWNER_MODE is on: requests without a token resolve to %s, "
            "so sign-out cannot work and the login screen is skipped. "
            "Set GUMMY_OWNER_MODE=false to use real accounts.",
            settings.gummy_owner_email,
        )


def assert_auth_safe(settings: Settings) -> None:
    """Fail fast if an insecure auth configuration would reach production.

    Three configurations would each disable authentication in practice, so each
    is a hard startup failure rather than a logged warning:

    * ``auth_dev_bypass`` — accepts a tenant id straight from a query parameter.
    * ``gummy_owner_mode`` — auto-authenticates every request as the owner.
    * a default/empty token-signing secret — anyone who reads this open-source
      repo could then mint a valid token for any user id.
    """
    if not settings.is_production:
        return

    if settings.auth_dev_bypass:
        raise RuntimeError(
            "auth_dev_bypass must be disabled in production (AUTH_DEV_BYPASS=false)."
        )
    if settings.gummy_owner_mode:
        raise RuntimeError(
            "gummy_owner_mode must be disabled in production "
            "(GUMMY_OWNER_MODE=false) — it signs every request in as the owner."
        )
    if settings.local_auth_secret in ("", "dev-insecure-change-me"):
        raise RuntimeError(
            "GUMMY_JWT_SECRET must be set to a strong random value in production; "
            "the default secret is public and would let anyone forge a token."
        )
