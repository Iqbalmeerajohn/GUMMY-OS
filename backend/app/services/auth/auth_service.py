"""Account lifecycle: sign-up, sign-in, Google linking, and session rotation.

Every function here runs on the **owner** session (see
``database.session.get_auth_sessionmaker``), because authentication has to find
an account *before* the acting tenant is known — and under RLS a tenant-scoped
session with no ``app.current_user_id`` set sees nothing at all. Consequently
every query in this module filters explicitly by email, id, or google_sub;
nothing here may return a set of rows to a caller.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.auth import password_service, token_service
from app.services.auth.google_oauth import GoogleIdentity

logger = logging.getLogger(__name__)

# One message for "no such account" and "wrong password" alike: distinguishing
# them turns the login form into an account-enumeration oracle.
_BAD_CREDENTIALS = "Incorrect email or password."


@dataclass(frozen=True)
class AuthResult:
    """A signed-in user plus the credentials issued for them."""

    user: User
    session: token_service.IssuedSession


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _invalid_credentials() -> AppError:
    return AppError(_BAD_CREDENTIALS, code="invalid_credentials", status_code=401)


async def _issue_session(
    session: AsyncSession, *, user: User, settings: Settings
) -> token_service.IssuedSession:
    """Mint an access/refresh pair and persist the refresh token's hash."""
    access_token, expires_in = token_service.create_access_token(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        settings=settings,
    )
    refresh = token_service.create_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=token_service.hash_refresh_token(refresh),
            expires_at=token_service.refresh_expiry(settings),
        )
    )
    user.last_login_at = datetime.now(UTC)
    await session.flush()
    return token_service.IssuedSession(
        access_token=access_token, refresh_token=refresh, expires_in=expires_in
    )


async def sign_up(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str | None,
    settings: Settings,
) -> AuthResult:
    """Create an account with a password and sign it in."""
    normalized = _normalize_email(email)
    user = User(
        email=normalized,
        password_hash=password_service.hash_password(password),
        display_name=(display_name or "").strip() or None,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            "An account with this email already exists.",
            code="email_taken",
            status_code=409,
        ) from exc

    issued = await _issue_session(session, user=user, settings=settings)
    await session.commit()
    return AuthResult(user=user, session=issued)


async def sign_in(
    session: AsyncSession, *, email: str, password: str, settings: Settings
) -> AuthResult:
    """Verify a password and issue a session."""
    normalized = _normalize_email(email)
    user = await session.scalar(select(User).where(User.email == normalized))
    if user is None or not password_service.verify_password(
        password, user.password_hash
    ):
        raise _invalid_credentials()

    # Transparently upgrade a hash stored under weaker parameters, now that we
    # hold the plaintext and have already proven it correct.
    if password_service.needs_rehash(user.password_hash):
        user.password_hash = password_service.hash_password(password)

    issued = await _issue_session(session, user=user, settings=settings)
    await session.commit()
    return AuthResult(user=user, session=issued)


async def sign_in_with_google(
    session: AsyncSession, *, identity: GoogleIdentity, settings: Settings
) -> AuthResult:
    """Sign in (or register) via a verified Google identity.

    Resolution order is ``google_sub`` first, then email. Matching on ``sub``
    before email means a user who changed their Google email still lands on the
    same account; falling back to email links Google to an account that was
    originally created with a password, instead of creating a duplicate.
    """
    user = await session.scalar(
        select(User).where(User.google_sub == identity.google_sub)
    )
    if user is None:
        user = await session.scalar(select(User).where(User.email == identity.email))
        if user is not None:
            user.google_sub = identity.google_sub

    if user is None:
        user = User(
            email=identity.email,
            google_sub=identity.google_sub,
            display_name=identity.display_name,
            avatar_url=identity.avatar_url,
            # No password: this account can only be reached through Google
            # until the user explicitly sets one.
            password_hash=None,
        )
        session.add(user)
        await session.flush()
    else:
        # Keep the profile fresh, but never overwrite a name the user set here
        # with Google's version.
        if identity.avatar_url:
            user.avatar_url = identity.avatar_url
        if identity.display_name and not user.display_name:
            user.display_name = identity.display_name

    issued = await _issue_session(session, user=user, settings=settings)
    await session.commit()
    return AuthResult(user=user, session=issued)


def _expired(record: RefreshToken, now: datetime) -> bool:
    """Whether a stored refresh token has passed its expiry.

    The stored timestamp is read back naive on backends without timezone-aware
    columns, and comparing that to an aware ``now`` raises rather than expiring
    the token — a crash instead of a 401. Assume UTC (which is what was written)
    rather than trusting the driver to say so.
    """
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now


async def refresh_session(
    session: AsyncSession, *, refresh_token: str, settings: Settings
) -> AuthResult:
    """Rotate a refresh token: revoke the presented one, issue a new pair.

    Rotation (rather than reuse) means a stolen refresh token is only usable
    until the legitimate client next refreshes, at which point the thief's copy
    is already revoked.
    """
    token_hash = token_service.hash_refresh_token(refresh_token)
    record = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    now = datetime.now(UTC)
    if record is None or record.revoked_at is not None or _expired(record, now):
        raise AppError(
            "This session has expired. Please sign in again.",
            code="invalid_refresh_token",
            status_code=401,
        )

    user = await session.get(User, record.user_id)
    if user is None:
        raise AppError(
            "This session has expired. Please sign in again.",
            code="invalid_refresh_token",
            status_code=401,
        )

    record.revoked_at = now
    issued = await _issue_session(session, user=user, settings=settings)
    await session.commit()
    return AuthResult(user=user, session=issued)


async def revoke_session(session: AsyncSession, *, refresh_token: str) -> None:
    """Sign out: revoke a single refresh token. Idempotent."""
    token_hash = token_service.hash_refresh_token(refresh_token)
    record = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if record is not None and record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        await session.commit()


async def get_or_create_owner(session: AsyncSession, *, email: str) -> User:
    """Resolve the single-user 'owner mode' account, creating it on first boot.

    Owner mode resolves a **real, persisted** user rather than a synthetic id
    (which is what ``auth_dev_bypass`` does). That distinction matters: memories
    written while running open locally stay owned by the same account after
    sign-in is switched on, instead of being stranded under a throwaway id.
    """
    normalized = _normalize_email(email)
    user = await session.scalar(select(User).where(User.email == normalized))
    if user is not None:
        return user
    user = User(email=normalized, display_name="Owner")
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        # Two workers booted at once; the other won. Re-read its row.
        await session.rollback()
        found = await session.scalar(select(User).where(User.email == normalized))
        if found is None:
            raise
        return found
    await session.commit()
    return user


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Fetch a user by id on the auth (owner) session."""
    return await session.get(User, user_id)
