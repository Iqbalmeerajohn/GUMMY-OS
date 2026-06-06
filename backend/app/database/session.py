"""Async database engine and a lightweight readiness check.

Day 1 wires only what the readiness probe needs: a lazily-created async engine and
a ``SELECT 1`` ping. The ORM base, session-per-request dependency, and migrations
arrive on Day 2. The engine is created lazily so the app boots even when no
database is configured (early local development).
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None


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
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        logger.info("database engine disposed")
