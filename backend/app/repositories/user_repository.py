"""Data-access for users, including the auth upsert (get-or-create by id)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    """Ensure a local users row keyed by the Supabase auth id (the JWT ``sub``).

    Creates the row on first authenticated request; refreshes the email if it
    changed. Email is unique + NOT NULL, so collisions with a *different*
    (legacy/dev) row fall back to an id-derived placeholder rather than crashing.
    """
    user = await get_user(session, user_id)
    if user is None:
        resolved = email or f"{user_id}@no-email.local"
        if email is not None:
            clash = await get_user_by_email(session, email)
            if clash is not None and clash.id != user_id:
                resolved = f"{user_id}@dup.local"
        user = User(id=user_id, email=resolved)
        session.add(user)
        await session.flush()
        return user

    if email is not None and user.email != email:
        clash = await get_user_by_email(session, email)
        if clash is None or clash.id == user_id:
            user.email = email
            await session.flush()
    return user
