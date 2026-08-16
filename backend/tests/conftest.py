"""Shared test fixtures.

Database tests run against an in-memory SQLite database (via aiosqlite) so the
suite needs no live Postgres. A StaticPool keeps a single shared connection, so
every session in a test sees the same data. The Postgres-only ``gen_random_uuid()``
server default is neutralized for SQLite — ids still come from the model's
Python-side ``uuid4`` default, so behavior is unchanged.
"""

from __future__ import annotations

import os

# Hermetic tests: ignore any developer `.env` database so the suite never depends
# on (or connects to) live infrastructure. Tests that need a database use the
# in-memory SQLite fixtures below. This must run before `app` is imported, since
# the settings singleton reads the environment at construction time.
os.environ["DATABASE_URL"] = ""
os.environ["DIRECT_DATABASE_URL"] = ""
# Auth in tests: enable the dev bypass so existing API tests keep passing the
# tenant via the legacy `user_id` query param. Token-path tests mint HS256 tokens
# against GUMMY_JWT_SECRET below, hermetically.
os.environ["AUTH_DEV_BYPASS"] = "true"
# Owner mode signs EVERY request in as the local owner. Left on, it would make
# the tenant-isolation and "requires authentication" tests pass vacuously, which
# is the opposite of what they exist to prove — so it is forced off here
# regardless of the developer's `.env`.
os.environ["GUMMY_OWNER_MODE"] = "false"
os.environ["GUMMY_JWT_SECRET"] = "test-local-jwt-secret"
# Never reach a live model from the suite: the developer `.env` selects Ollama,
# which would make tests depend on a running daemon.
os.environ["EMBEDDINGS_PROVIDER"] = "fake"
os.environ["LLM_PROVIDER"] = "fake"

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app import models as _models  # noqa: F401  registers tables on Base.metadata
from app.database.base import Base
from app.database.session import get_auth_sessionmaker, get_db
from app.main import app
from app.models.user import User
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.factory import get_embedding_service
from app.services.embeddings.fake_provider import FakeEmbeddingProvider
from app.services.llm.factory import get_llm_provider
from app.services.llm.fake_provider import FakeLLMProvider


def _make_sqlite_compatible() -> None:
    """Drop Postgres-only server defaults so create_all works on SQLite."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            default = column.server_default
            if default is not None and "gen_random_uuid" in str(
                getattr(default, "arg", "")
            ):
                column.server_default = None


@pytest_asyncio.fixture
async def sessionmaker_fixture() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    _make_sqlite_compatible()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with sessionmaker_fixture() as session:
        yield session


@pytest_asyncio.fixture
async def seed_user(
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
) -> uuid.UUID:
    async with sessionmaker_fixture() as session:
        user = User(email="tester@example.com")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


@pytest_asyncio.fixture
async def api_client(
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        async with sessionmaker_fixture() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    # Token-path auth upserts the user via the auth sessionmaker — point it at the
    # same in-memory SQLite engine so it shares the test database.
    app.dependency_overrides[get_auth_sessionmaker] = lambda: sessionmaker_fixture
    app.dependency_overrides[get_embedding_service] = lambda: EmbeddingService(
        FakeEmbeddingProvider()
    )
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        reply="You are preparing for Qualcomm."
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An httpx client wired directly to the ASGI app (no database)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
