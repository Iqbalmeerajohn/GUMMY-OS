"""Data-access for users, including the auth upsert (get-or-create by id)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.user import User


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    """Fetch a user by primary key."""
    return await session.get(User, user_id)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Fetch a user by email (the unique login identity)."""
    return await session.scalar(select(User).where(User.email == email))


async def upsert_user(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    email: str | None,
) -> User:
    """Ensure a local users row keyed by the Supabase auth id (JWT ``sub``).

    Resolution order:

    1. By id (the ``sub``) — the normal path; the row already exists.
    2. Otherwise insert it. Email is globally unique, so if a *different*
       account already owns this email we surface a clean 409 instead of a
       raw IntegrityError.

    Note: a by-email lookup cannot help reconcile a foreign-owned row here —
    the ``users`` RLS policy (``id = current_user_id``) hides any row owned by
    another id from this tenant-scoped session, so the conflict is only
    observable as the insert's unique-constraint violation. The fix for that
    conflict is identity reconciliation at the data layer, not in this path.
    """
    user = await get_user(session, user_id)
    if user is not None:
        # Same-tenant email refresh. A foreign owner of the new email is
        # invisible under RLS, so guard the flush and keep the old email
        # rather than 500 if the unique index rejects it.
        if email is not None and user.email != email:
            user.email = email
            try:
                async with session.begin_nested():
                    await session.flush()
            except IntegrityError:
                await session.refresh(user)
        return user

    resolved = email or f"{user_id}@no-email.local"
    user = User(id=user_id, email=resolved)
    session.add(user)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError as exc:
        raise AppError(
            "This email is already linked to a different account.",
            code="email_identity_conflict",
            status_code=409,
        ) from exc
    return user
