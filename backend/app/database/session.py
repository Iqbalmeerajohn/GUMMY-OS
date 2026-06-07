"""Async database engine, session factory, and the request-scoped dependency.

The engine and sessionmaker are created lazily so the app boots even when no
database is configured (early local development). ``get_db`` is the FastAPI
dependency that yields a transactional ``AsyncSession`` per request; services are
responsible for committing their unit of work, and any unhandled error rolls back.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.tenant_context import get_current_user_id, set_current_user_id

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


@event.listens_for(Session, "after_begin")
def _set_tenant_guc(session: Session, transaction: Any, connection: Connection) -> None:
    """Set the tenant GUC at the start of every PostgreSQL transaction.

    Read by RLS policies as ``current_setting('app.current_user_id', true)``.
    No-op on non-PostgreSQL backends (e.g. the SQLite test database), so the
    fast suite is unaffected. Runs once per transaction, which is required —
    services commit multiple times per request and Supabase's transaction
    pooler does not carry session-level settings across transactions.
    """
    if connection.dialect.name != "postgresql":
        return
    user_id = get_current_user_id()
    if user_id is None:
        return
    connection.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": str(user_id)},
    )


def get_engine() -> AsyncEngine | None:
    """Return the shared async engine, or None if no database is configured."""
    global _engine
    url = get_settings().async_database_url
    if url is None:
        return None
    if _engine is None:
        _engine = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
        )
        logger.info("database engine initialized")
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession] | None:
    """Return the shared session factory, or None if no database is configured."""
    global _sessionmaker
    engine = get_engine()
    if engine is None:
        return None
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


def get_auth_sessionmaker() -> async_sessionmaker[AsyncSession] | None:
    """Sessionmaker for the pre-request user upsert.

    Deliberately separate from ``get_db`` and never tenant-scoped: the auth
    dependency resolves the user *before* the request's (future RLS-scoped)
    session exists. Returns None when no database is configured.
    """
    return get_sessionmaker()


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield a session, rolling back on unhandled errors."""
    sessionmaker = get_sessionmaker()
    if sessionmaker is None:
        raise AppError(
            "Database is not configured.",
            code="database_unavailable",
            status_code=503,
        )
    async with sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            # Clear the tenant so it never leaks to the next request on a
            # keep-alive connection (every data request goes through get_db).
            set_current_user_id(None)


async def check_database() -> tuple[str, str | None]:
    """Ping the database for the readiness probe.

    Returns a ``(status, detail)`` tuple where status is one of
    ``"ok"`` | ``"not_configured"`` | ``"unavailable"``.
    """
    if not get_settings().is_database_configured:
        return "not_configured", "DATABASE_URL not set"
    engine = get_engine()
    if engine is None:
        return "not_configured", "DATABASE_URL not set"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("database readiness check failed: %s", exc)
        return "unavailable", str(exc)
    return "ok", None


async def dispose_engine() -> None:
    """Dispose the engine on shutdown (releases pooled connections)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
        logger.info("database engine disposed")
