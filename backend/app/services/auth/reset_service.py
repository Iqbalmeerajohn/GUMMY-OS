"""Password recovery: issue a reset token, and redeem it.

Runs on the **owner** session for the same reason the rest of
:mod:`app.services.auth` does — a user who has forgotten their password has no
session, so no tenant context exists and an RLS-scoped connection would see
nothing. Every query here filters explicitly by email or token hash; nothing
returns a set of rows to a caller.

The token itself never touches the database in the clear:

    secrets.token_urlsafe  ->  raw token  ->  emailed link
                                  |
                              sha256()
                                  |
                            stored token_hash

Redemption hashes what was presented and looks that up, so a dump of
``password_reset_tokens`` grants nobody a reset. This mirrors
``token_service.hash_refresh_token`` exactly, and for the same reason: the token
is 256 bits of cryptographic randomness with no guessable structure, so a plain
SHA-256 is right and the lookup stays one indexed read.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.auth import mailer, password_service, token_service

logger = logging.getLogger(__name__)

# Returned for every forgot-password request, whether or not the address maps to
# an account. Distinguishing the two turns this endpoint into a free
# account-enumeration oracle for anyone who can send an HTTP request.
GENERIC_RESET_RESPONSE = (
    "If an account exists for this email, password reset instructions have "
    "been sent."
)

# One message for every way a token can fail — unknown, expired, already spent,
# or belonging to a deleted user. Telling them apart would let an attacker probe
# which tokens once existed.
_INVALID_TOKEN = "This password reset link is invalid or has expired."


def _invalid_token() -> AppError:
    return AppError(_INVALID_TOKEN, code="invalid_reset_token", status_code=400)


def create_reset_token() -> str:
    """A new opaque reset token (URL-safe, 256 bits of entropy)."""
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    """SHA-256 of a reset token — what actually gets stored."""
    return token_service.hash_refresh_token(token)


def _expired(record: PasswordResetToken, now: datetime) -> bool:
    """Whether a stored reset token has passed its expiry.

    SQLite reads the timestamp back naive, and comparing that to an aware
    ``now`` raises rather than expiring the token — a 500 instead of a clean
    rejection. Assume UTC (which is what was written), exactly as
    ``auth_service._expired`` does for refresh tokens.
    """
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= now


def _reset_link(token: str, *, settings: Settings) -> str:
    return f"{settings.frontend_url.rstrip('/')}/reset-password?token={token}"


def _reset_email(link: str, *, settings: Settings) -> str:
    minutes = settings.password_reset_ttl_minutes
    return (
        "Someone asked to reset the password for your GUMMY account.\n\n"
        f"{link}\n\n"
        f"This link works once and expires in {minutes} minutes.\n"
        "If this wasn't you, you can ignore this email — nothing has changed."
    )


async def request_password_reset(
    session: AsyncSession, *, email: str, settings: Settings
) -> None:
    """Issue and deliver a reset link, if the address maps to an account.

    Returns ``None`` in every case, including no such account. The caller must
    respond identically either way — the silence here is the anti-enumeration
    property, and it only holds if nothing above leaks the difference.
    """
    normalized = email.strip().lower()
    user = await session.scalar(select(User).where(User.email == normalized))

    if user is None:
        # Logged at INFO because this is useful signal locally and reveals
        # nothing to the caller, who receives the same response regardless.
        logger.info("password reset requested for unknown address")
        return

    if user.password_hash is None and user.google_sub is not None:
        # A Google-only account has no password to reset. Setting one here
        # would silently convert it into a password account, so the honest
        # move is to do nothing and still say nothing.
        logger.info("password reset requested for a Google-only account")
        return

    # Any earlier link the user has is superseded. Without this, a second
    # request leaves the first link live, so the window an attacker has to use
    # an intercepted one is as long as the user keeps clicking "resend".
    await session.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=datetime.now(UTC))
    )

    raw = create_reset_token()
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_reset_token(raw),
            expires_at=datetime.now(UTC)
            + timedelta(minutes=settings.password_reset_ttl_minutes),
        )
    )
    await session.commit()

    mailer.send(
        mailer.Message(
            to=user.email,
            subject="Reset your GUMMY password",
            body=_reset_email(_reset_link(raw, settings=settings), settings=settings),
        ),
        settings=settings,
    )


async def reset_password(
    session: AsyncSession, *, token: str, new_password: str, settings: Settings
) -> User:
    """Redeem a reset token and set a new password.

    On success the token is spent and every refresh token for the account is
    revoked, so a session an attacker opened with the old password dies with it.
    """
    record = await session.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_reset_token(token)
        )
    )
    now = datetime.now(UTC)
    if record is None or record.used_at is not None or _expired(record, now):
        raise _invalid_token()

    user = await session.get(User, record.user_id)
    if user is None:
        raise _invalid_token()

    user.password_hash = password_service.hash_password(new_password)
    record.used_at = now

    # Password changed, so every existing session is suspect. Revoking rather
    # than deleting keeps a replayed token detectable instead of merely
    # "not found".
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await session.commit()

    logger.info("password reset completed for user_id=%s", user.id)
    return user
