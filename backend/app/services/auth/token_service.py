"""GUMMY-issued access and refresh tokens.

Access tokens are self-contained HS256 JWTs verified locally — no database read
and no network call on the request path, which is what keeps authentication off
the latency budget. Refresh tokens are opaque random strings stored **hashed**,
so they can be revoked and cannot be replayed from a database dump.

Claims are the conventional set (``sub``, ``email``, ``exp``, ``aud``, plus
``user_metadata.full_name``), so any standard JWT client can read them.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings

# Audience claim on every token this app mints; verification requires it, so a
# token issued for anything else is rejected outright.
TOKEN_AUDIENCE = "gummy-os"
ALGORITHM = "HS256"


@dataclass(frozen=True)
class IssuedSession:
    """A freshly minted credential pair."""

    access_token: str
    refresh_token: str
    expires_in: int  # access-token lifetime, seconds


def hash_refresh_token(token: str) -> str:
    """SHA-256 of a refresh token — what actually gets stored.

    A plain hash (no salt/KDF) is correct here and not a shortcut: the token is
    128 bits of cryptographic randomness, so it has no guessable structure for a
    brute-force or rainbow attack to exploit, and the lookup must be a single
    indexed read by hash.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_refresh_token() -> str:
    """A new opaque refresh token (URL-safe, 256 bits of entropy)."""
    return secrets.token_urlsafe(32)


def create_access_token(
    *,
    user_id: uuid.UUID,
    email: str | None,
    display_name: str | None,
    settings: Settings,
) -> tuple[str, int]:
    """Mint a signed access token. Returns ``(token, expires_in_seconds)``."""
    ttl = timedelta(minutes=settings.gummy_access_token_ttl_minutes)
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": str(user_id),
        "aud": TOKEN_AUDIENCE,
        "iss": settings.gummy_jwt_issuer,
        "iat": now,
        "exp": now + ttl,
    }
    if email:
        payload["email"] = email
    if display_name:
        # The shape `_extract_name` in core.security reads.
        payload["user_metadata"] = {"full_name": display_name}
    token = jwt.encode(payload, settings.local_auth_secret, algorithm=ALGORITHM)
    return token, int(ttl.total_seconds())


def refresh_expiry(settings: Settings) -> datetime:
    """Absolute expiry for a newly issued refresh token."""
    return datetime.now(UTC) + timedelta(days=settings.gummy_refresh_token_ttl_days)
