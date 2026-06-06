"""Async database engine, session factory, and the request-scoped dependency.

The engine and sessionmaker are created lazily so the app boots even when no
database is configured (early local development). ``get_db`` is the FastAPI
dependency that yields a transactional ``AsyncSession`` per request; services are
responsible for committing their unit of work, and any unhandled error rolls back.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


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
