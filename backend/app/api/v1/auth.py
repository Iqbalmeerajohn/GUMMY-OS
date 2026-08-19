"""Authentication endpoints — GUMMY as its own identity provider.

Password sign-up/sign-in, Google OAuth, session refresh, and sign-out. Every
handler runs on the auth (owner) session, because a sign-in must resolve an
account before the acting tenant — and therefore before RLS — is established.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import AuthSessionmakerDep, CurrentUserDep, SettingsDep
from app.core.config import Settings
from app.core.exceptions import AppError
from app.models.user import User
from app.schemas.auth import (
    AuthConfigResponse,
    ForgotPasswordRequest,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    SessionResponse,
    SignInRequest,
    SignUpRequest,
    UserProfile,
)
from app.services.auth import auth_service, google_oauth, reset_service
from app.services.auth.auth_service import AuthResult
from app.services.auth.mailer import MailDeliveryError

router = APIRouter(prefix="/auth", tags=["auth"])


def _profile(user: User) -> UserProfile:
    return UserProfile(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
    )


def _session_response(result: AuthResult) -> SessionResponse:
    return SessionResponse(
        access_token=result.session.access_token,
        refresh_token=result.session.refresh_token,
        expires_in=result.session.expires_in,
        user=_profile(result.user),
    )


async def _open(
    sessionmaker: async_sessionmaker[AsyncSession] | None,
) -> AsyncSession:
    if sessionmaker is None:
        raise AppError(
            "Database is not configured.",
            code="database_unavailable",
            status_code=503,
        )
    return sessionmaker()


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config(settings: SettingsDep) -> AuthConfigResponse:
    """Which sign-in methods this server actually supports.

    The client calls this before rendering the login screen so it never offers
    a Google button that the server has no credentials to honour.
    """
    return AuthConfigResponse(
        google_enabled=settings.google_oauth_enabled,
        owner_mode=settings.gummy_owner_mode,
        email_console_mode=settings.auth_email_console_mode,
    )


@router.post(
    "/signup",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def sign_up(
    body: SignUpRequest,
    settings: SettingsDep,
    sessionmaker: AuthSessionmakerDep,
) -> SessionResponse:
    """Create an account with an email and password, and sign it in."""
    session = await _open(sessionmaker)
    async with session:
        result = await auth_service.sign_up(
            session,
            email=body.email,
            password=body.password,
            display_name=body.display_name,
            settings=settings,
        )
        return _session_response(result)


@router.post("/login", response_model=SessionResponse)
async def sign_in(
    body: SignInRequest,
    settings: SettingsDep,
    sessionmaker: AuthSessionmakerDep,
) -> SessionResponse:
    """Exchange an email and password for a session."""
    session = await _open(sessionmaker)
    async with session:
        result = await auth_service.sign_in(
            session,
            email=body.email,
            password=body.password,
            settings=settings,
        )
        return _session_response(result)


@router.post("/refresh", response_model=SessionResponse)
async def refresh(
    body: RefreshRequest,
    settings: SettingsDep,
    sessionmaker: AuthSessionmakerDep,
) -> SessionResponse:
    """Rotate a refresh token into a fresh access/refresh pair."""
    session = await _open(sessionmaker)
    async with session:
        result = await auth_service.refresh_session(
            session, refresh_token=body.refresh_token, settings=settings
        )
        return _session_response(result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(
    body: RefreshRequest,
    sessionmaker: AuthSessionmakerDep,
) -> None:
    """Revoke a refresh token. Idempotent, and never reveals whether it existed."""
    session = await _open(sessionmaker)
    async with session:
        await auth_service.revoke_session(session, refresh_token=body.refresh_token)


# ── Password recovery ────────────────────────────────────────────────────────


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    body: ForgotPasswordRequest,
    settings: SettingsDep,
    sessionmaker: AuthSessionmakerDep,
) -> MessageResponse:
    """Send a password reset link, if the address maps to an account.

    Always returns the same message. An endpoint that answered differently for
    a known and an unknown address would be a free account-enumeration oracle,
    so the response deliberately carries no information about the outcome.
    """
    session = await _open(sessionmaker)
    async with session:
        try:
            await reset_service.request_password_reset(
                session, email=body.email, settings=settings
            )
        except MailDeliveryError as exc:
            # Only reachable in SMTP mode. The user is told delivery failed
            # rather than being left waiting for mail that will never arrive —
            # and this leaks nothing, since it happens after the account was
            # already resolved and says nothing about which case it was.
            raise AppError(
                "Could not send the reset email. Please try again later.",
                code="email_delivery_failed",
                status_code=502,
            ) from exc
    return MessageResponse(message=reset_service.GENERIC_RESET_RESPONSE)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest,
    settings: SettingsDep,
    sessionmaker: AuthSessionmakerDep,
) -> MessageResponse:
    """Redeem a reset token and set a new password.

    On success the token is spent and every session for the account is revoked.
    No session is issued here: the user signs in with the new password, which
    proves the reset worked and matches how the rest of this app treats a
    password as the thing that mints a session.
    """
    session = await _open(sessionmaker)
    async with session:
        await reset_service.reset_password(
            session,
            token=body.token,
            new_password=body.new_password,
            settings=settings,
        )
    return MessageResponse(message="Your password has been reset. You can now sign in.")


@router.get("/me", response_model=UserProfile)
async def me(user: CurrentUserDep) -> UserProfile:
    """The currently authenticated account."""
    return UserProfile(
        id=user.id,
        email=user.email or "",
        display_name=user.display_name,
    )


# ── Google OAuth ─────────────────────────────────────────────────────────────


@router.get("/google/start")
async def google_start(
    settings: SettingsDep,
    next: Annotated[str, Query(description="Path to return to after sign-in.")] = "/",
) -> RedirectResponse:
    """Begin Google sign-in by redirecting to Google's consent screen."""
    state = google_oauth.create_state(settings, next_path=next)
    return RedirectResponse(google_oauth.authorization_url(settings, state=state))


@router.get("/google/callback")
async def google_callback(
    settings: SettingsDep,
    sessionmaker: AuthSessionmakerDep,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Complete Google sign-in and hand the session to the frontend.

    Ends in a browser redirect rather than JSON, because this URL is loaded by
    Google's redirect and not by application code. Tokens ride in the URL
    fragment (``#``), which browsers never send to servers and which is absent
    from server logs and ``Referer`` headers — the query string would leak them
    into both.
    """
    if error:
        return _redirect_failure(settings, reason=error)

    next_path = google_oauth.verify_state(settings, state)
    if not code:
        return _redirect_failure(settings, reason="missing_code")

    identity = await google_oauth.exchange_code(settings, code=code)
    session = await _open(sessionmaker)
    async with session:
        result = await auth_service.sign_in_with_google(
            session, identity=identity, settings=settings
        )

    fragment = (
        f"access_token={result.session.access_token}"
        f"&refresh_token={result.session.refresh_token}"
        f"&expires_in={result.session.expires_in}"
    )
    target = f"{settings.frontend_url.rstrip('/')}/auth/callback"
    return RedirectResponse(f"{target}?next={next_path}#{fragment}")


def _redirect_failure(settings: Settings, *, reason: str) -> RedirectResponse:
    """Send the browser back to the login screen with a machine-readable reason."""
    base = settings.frontend_url.rstrip("/")
    return RedirectResponse(f"{base}/login?error={reason}")
