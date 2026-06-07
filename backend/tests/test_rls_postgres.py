"""Row-Level Security enforcement tests (PostgreSQL only).

Skipped unless ``RUN_RLS_PG_TESTS=1`` and ``RLS_TEST_DSN`` (a **non-bypass** role,
e.g. ``gummy_app``, against a database where migration 0005 is applied) are set.
RLS is not enforceable on SQLite, so this never runs in the fast suite.

Self-contained: as the app role under its own tenant GUC, it inserts a user +
memory, then proves a second tenant cannot see them and that an unset GUC returns
nothing.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

pytestmark = pytest.mark.skipif(
    not (os.getenv("RUN_RLS_PG_TESTS") and os.getenv("RLS_TEST_DSN")),
    reason="set RUN_RLS_PG_TESTS=1 and RLS_TEST_DSN (gummy_app DSN) to run",
)


async def _set_tenant(session: AsyncSession, user_id: uuid.UUID | None) -> None:
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, false)"),
        {"uid": str(user_id) if user_id else ""},
    )


async def test_tenant_isolation_under_rls() -> None:
    dsn = os.environ["RLS_TEST_DSN"]
    engine = create_async_engine(dsn, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    alice = uuid.uuid4()
    bob = uuid.uuid4()
    try:
        # Alice creates herself + a memory (WITH CHECK passes: row.user == GUC).
        async with maker() as s:
            await _set_tenant(s, alice)
            await s.execute(
                text("INSERT INTO users (id, email) VALUES (:id, :e)"),
                {"id": str(alice), "e": f"{alice}@rls.test"},
            )
            await s.execute(
                text(
                    "INSERT INTO memories (user_id, category, content, "
                    "importance_score, confidence_score, status) "
                    "VALUES (:u, 'career', 'alice-secret', 0.5, 0.5, 'active')"
                ),
                {"u": str(alice)},
            )
            await s.commit()

        # Alice sees her row.
        async with maker() as s:
            await _set_tenant(s, alice)
            count = await s.scalar(text("SELECT count(*) FROM memories"))
            assert count == 1

        # Bob sees nothing of Alice's (isolation).
        async with maker() as s:
            await _set_tenant(s, bob)
            count = await s.scalar(text("SELECT count(*) FROM memories"))
            assert count == 0

        # Unset GUC -> fail closed (no rows).
        async with maker() as s:
            await _set_tenant(s, None)
            count = await s.scalar(text("SELECT count(*) FROM memories"))
            assert count == 0

        # Cross-tenant INSERT is rejected by WITH CHECK.
        async with maker() as s:
            await _set_tenant(s, bob)
            with pytest.raises(Exception):  # noqa: B017,PT011 - RLS WITH CHECK
                await s.execute(
                    text(
                        "INSERT INTO memories (user_id, category, content, "
                        "importance_score, confidence_score, status) "
                        "VALUES (:u, 'career', 'forged', 0.5, 0.5, 'active')"
                    ),
                    {"u": str(alice)},  # not bob's id
                )
                await s.commit()
    finally:
        # Cleanup as Alice.
        async with maker() as s:
            await _set_tenant(s, alice)
            await s.execute(
                text("DELETE FROM memories WHERE user_id = :u"), {"u": str(alice)}
            )
            await s.execute(text("DELETE FROM users WHERE id = :u"), {"u": str(alice)})
            await s.commit()
        await engine.dispose()
