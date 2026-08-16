"""Google OAuth 2.0 — direct, with no identity-provider middleman.

The full authorization-code flow in three calls: build the consent URL, exchange
the returned code for tokens, and read the user's identity out of the ID token.

Two decisions worth stating:

* **The ``state`` parameter is a signed, short-lived JWT rather than a server-side
  session entry.** It carries its own expiry and is verified with the app secret,
  so CSRF protection needs no shared store — which matters because the callback
  may be handled by a different worker process than the one that started the flow.

* **The ID token is decoded without signature verification.** This is Google's own
  documented guidance for the authorization-code flow: the token arrives in the
  body of a direct TLS response from Google's token endpoint, so the channel
  already authenticates it. Signature verification is required only when a token
  arrives from an untrusted party (e.g. the implicit flow). Doing it here would
  add a JWKS fetch to the login path for no security gain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import Settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_TIMEOUT_SECONDS = 15.0

# Identity only. Additional scopes (Gmail, Calendar, Drive) are requested later
# by the Connectors layer with their own explicit consent screen, so signing in
# never silently grants data access.
_SCOPES = ("openid", "email", "profile")

# The state token is only alive between the redirect to Google and the callback.
_STATE_TTL_MINUTES = 10
_STATE_AUDIENCE = "gummy-oauth-state"


@dataclass(frozen=True)
class GoogleIdentity:
    """The verified identity Google returned."""

    google_sub: str
    email: str
    display_name: str | None
    avatar_url: str | None


def _require_config(settings: Settings) -> tuple[str, str]:
    if not settings.google_oauth_enabled:
        raise AppError(
            "Google sign-in is not configured on this server. Set "
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
            code="google_oauth_unconfigured",
            status_code=503,
        )
    # Narrowed by google_oauth_enabled, which requires both to be set.
    return str(settings.google_client_id), str(settings.google_client_secret)


def create_state(settings: Settings, *, next_path: str) -> str:
    """Sign a short-lived state token carrying the post-login destination."""
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "aud": _STATE_AUDIENCE,
            "iat": now,
            "exp": now + timedelta(minutes=_STATE_TTL_MINUTES),
            "next": next_path,
        },
        settings.local_auth_secret,
        algorithm="HS256",
    )


def verify_state(settings: Settings, state: str | None) -> str:
    """Verify the returned state and recover the destination path.

    Raises 400 on a missing, expired, or forged state — that is the CSRF check.
    """
    if not state:
        raise AppError(
            "Missing OAuth state.", code="oauth_state_missing", status_code=400
        )
    try:
        claims = jwt.decode(
            state,
            settings.local_auth_secret,
            algorithms=["HS256"],
            audience=_STATE_AUDIENCE,
        )
    except jwt.InvalidTokenError as exc:
        raise AppError(
            "The sign-in request expired or was invalid. Please try again.",
            code="oauth_state_invalid",
            status_code=400,
        ) from exc
    next_path = claims.get("next")
    return next_path if isinstance(next_path, str) else "/"


def authorization_url(settings: Settings, *, state: str) -> str:
    """The Google consent URL to redirect the browser to."""
    client_id, _ = _require_config(settings)
    params = {
        "client_id": client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(_SCOPES),
        "state": state,
        # Google only returns a refresh token on the first consent unless we ask
        # for offline access; harmless for identity-only, and required once the
        # Connectors layer starts reading Gmail/Calendar on the user's behalf.
        "access_type": "offline",
        # Ensures a returning user still gets an account chooser rather than
        # being silently signed in as whoever the browser last used.
        "prompt": "select_account",
    }
    return f"{_AUTH_ENDPOINT}?{urlencode(params)}"


async def exchange_code(settings: Settings, *, code: str) -> GoogleIdentity:
    """Trade an authorization code for the user's Google identity."""
    client_id, client_secret = _require_config(settings)
    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(_TOKEN_ENDPOINT, data=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Google token exchange failed (%s): %s",
            exc.response.status_code,
            exc.response.text[:300],
        )
        raise AppError(
            "Google sign-in failed. Please try again.",
            code="google_exchange_failed",
            status_code=401,
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("Google token exchange transport error: %s", exc)
        raise AppError(
            "Could not reach Google to complete sign-in.",
            code="google_unreachable",
            status_code=503,
        ) from exc

    id_token = response.json().get("id_token")
    if not id_token:
        raise AppError(
            "Google did not return an identity token.",
            code="google_exchange_failed",
            status_code=401,
        )
    return _identity_from_id_token(id_token)


def _identity_from_id_token(id_token: str) -> GoogleIdentity:
    """Read identity claims from Google's ID token (see module docstring)."""
    try:
        claims = jwt.decode(
            id_token,
            options={"verify_signature": False, "verify_aud": False},
        )
    except jwt.InvalidTokenError as exc:
        raise AppError(
            "Google returned a malformed identity token.",
            code="google_exchange_failed",
            status_code=401,
        ) from exc

    sub = claims.get("sub")
    email = claims.get("email")
    if not sub or not email:
        raise AppError(
            "Google did not share an email address for this account.",
            code="google_email_missing",
            status_code=401,
        )
    return GoogleIdentity(
        google_sub=str(sub),
        email=str(email).lower(),
        display_name=(
            str(claims["name"]) if isinstance(claims.get("name"), str) else None
        ),
        avatar_url=(
            str(claims["picture"]) if isinstance(claims.get("picture"), str) else None
        ),
    )
