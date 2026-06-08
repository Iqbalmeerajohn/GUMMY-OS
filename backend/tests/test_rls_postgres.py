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

from app.repositories import conversation_search_repository as search_repo

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


# Every Phase 2 tenant table, checked for isolation + fail-closed in one sweep.
_PHASE2_TABLES = (
    "conversations",
    "messages",
    "conversation_summaries",
    "conversation_summary_embeddings",
    "memory_sources",
)

# A 384-dim zero vector (EMBEDDING_DIMENSION) for the summary-embedding insert.
_ZERO_VECTOR = "[" + ",".join(["0"] * 384) + "]"


async def test_conversation_tables_isolation_under_rls() -> None:
    """Phase 2 M1 gate: every new Phase 2 table is RLS-isolated.

    Inserts a full FK chain under Alice (conversation -> message -> summary ->
    summary embedding, plus memory -> memory_source), then proves on ALL five
    tables: tenant isolation, fail-closed on unset GUC, and WITH CHECK rejection
    of a forged cross-tenant insert — under the non-bypass ``gummy_app`` role.
    """
    dsn = os.environ["RLS_TEST_DSN"]
    engine = create_async_engine(dsn, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    alice = uuid.uuid4()
    bob = uuid.uuid4()
    conv = uuid.uuid4()
    msg = uuid.uuid4()
    mem = uuid.uuid4()
    summ = uuid.uuid4()
    try:
        # Alice builds the whole chain across all five tables.
        async with maker() as s:
            await _set_tenant(s, alice)
            await s.execute(
                text("INSERT INTO users (id, email) VALUES (:id, :e)"),
                {"id": str(alice), "e": f"{alice}@rls.test"},
            )
            await s.execute(
                text(
                    "INSERT INTO conversations (id, user_id, status, "
                    "agent_context, pinned, message_count) "
                    "VALUES (:c, :u, 'active', 'general', false, 0)"
                ),
                {"c": str(conv), "u": str(alice)},
            )
            await s.execute(
                text(
                    "INSERT INTO messages (id, conversation_id, user_id, seq, "
                    "role, content) VALUES (:m, :c, :u, 1, 'user', 'alice-msg')"
                ),
                {"m": str(msg), "c": str(conv), "u": str(alice)},
            )
            await s.execute(
                text(
                    "INSERT INTO memories (id, user_id, category, content, "
                    "importance_score, confidence_score, status) "
                    "VALUES (:mem, :u, 'career', 'alice-mem', 0.5, 0.5, 'active')"
                ),
                {"mem": str(mem), "u": str(alice)},
            )
            await s.execute(
                text(
                    "INSERT INTO conversation_summaries (id, conversation_id, "
                    "user_id, summary_type, content, covers_through_message_id, "
                    "version_number) VALUES (:sm, :c, :u, 'rolling', "
                    "'alice-summary', :msg, 1)"
                ),
                {"sm": str(summ), "c": str(conv), "u": str(alice), "msg": str(msg)},
            )
            await s.execute(
                text(
                    "INSERT INTO conversation_summary_embeddings (summary_id, "
                    "user_id, embedding_model, embedding_dimension, content_hash, "
                    "embedding_vector) VALUES (:sm, :u, 'test', 384, 'h', "
                    "CAST(:vec AS vector))"
                ),
                {"sm": str(summ), "u": str(alice), "vec": _ZERO_VECTOR},
            )
            await s.execute(
                text(
                    "INSERT INTO memory_sources (user_id, memory_id, "
                    "conversation_id, message_id, source_kind) "
                    "VALUES (:u, :mem, :c, :msg, 'conversation')"
                ),
                {"u": str(alice), "mem": str(mem), "c": str(conv), "msg": str(msg)},
            )
            await s.commit()

        # Alice sees exactly one row in every table.
        async with maker() as s:
            await _set_tenant(s, alice)
            for table in _PHASE2_TABLES:
                count = await s.scalar(text(f"SELECT count(*) FROM {table}"))
                assert count == 1, f"alice should see her {table} row"

        # Bob sees nothing on any table (isolation).
        async with maker() as s:
            await _set_tenant(s, bob)
            for table in _PHASE2_TABLES:
                count = await s.scalar(text(f"SELECT count(*) FROM {table}"))
                assert count == 0, f"bob must not see alice's {table}"

        # Unset GUC -> fail closed (no rows) on every table.
        async with maker() as s:
            await _set_tenant(s, None)
            for table in _PHASE2_TABLES:
                count = await s.scalar(text(f"SELECT count(*) FROM {table}"))
                assert count == 0, f"unset GUC must hide {table}"

        # WITH CHECK: Bob forging Alice's user_id is rejected (conversations).
        async with maker() as s:
            await _set_tenant(s, bob)
            with pytest.raises(Exception):  # noqa: B017,PT011 - RLS WITH CHECK
                await s.execute(
                    text(
                        "INSERT INTO conversations (user_id, status, "
                        "agent_context, pinned, message_count) "
                        "VALUES (:u, 'active', 'general', false, 0)"
                    ),
                    {"u": str(alice)},  # not bob's id
                )
                await s.commit()

        # WITH CHECK on a second table (memory_sources) — Bob forging Alice.
        async with maker() as s:
            await _set_tenant(s, bob)
            with pytest.raises(Exception):  # noqa: B017,PT011 - RLS WITH CHECK
                await s.execute(
                    text(
                        "INSERT INTO memory_sources (user_id, memory_id, "
                        "source_kind) VALUES (:u, :mem, 'conversation')"
                    ),
                    {"u": str(alice), "mem": str(mem)},  # not bob's id
                )
                await s.commit()
    finally:
        # Cleanup as Alice. memory_sources/messages/summaries/embeddings cascade
        # from their parents; delete conversation + memory + user explicitly.
        async with maker() as s:
            await _set_tenant(s, alice)
            await s.execute(
                text("DELETE FROM conversations WHERE user_id = :u"),
                {"u": str(alice)},
            )
            await s.execute(
                text("DELETE FROM memories WHERE user_id = :u"),
                {"u": str(alice)},
            )
            await s.execute(
                text("DELETE FROM users WHERE id = :u"), {"u": str(alice)}
            )
            await s.commit()
        await engine.dispose()


# A non-zero unit-ish vector (avoids pgvector's zero-vector cosine NaN).
_SEARCH_VECTOR_SQL = "[" + ",".join(["1"] + ["0"] * 383) + "]"
_SEARCH_QUERY_VECTOR = [1.0] + [0.0] * 383


async def _seed_searchable(
    maker: async_sessionmaker[AsyncSession], tenant: uuid.UUID
) -> uuid.UUID:
    """Seed one tenant's conversation + message + summary + embedding."""
    conv = uuid.uuid4()
    summary = uuid.uuid4()
    async with maker() as s:
        await _set_tenant(s, tenant)
        await s.execute(
            text("INSERT INTO users (id, email) VALUES (:id, :e)"),
            {"id": str(tenant), "e": f"{tenant}@rls.test"},
        )
        await s.execute(
            text(
                "INSERT INTO conversations (id, user_id, status, agent_context, "
                "pinned, message_count) VALUES (:c, :u, 'active', 'general', "
                "false, 1)"
            ),
            {"c": str(conv), "u": str(tenant)},
        )
        await s.execute(
            text(
                "INSERT INTO messages (conversation_id, user_id, seq, role, "
                "content) VALUES (:c, :u, 1, 'user', 'roadmap planning session')"
            ),
            {"c": str(conv), "u": str(tenant)},
        )
        await s.execute(
            text(
                "INSERT INTO conversation_summaries (id, conversation_id, "
                "user_id, summary_type, content, version_number) VALUES "
                "(:sm, :c, :u, 'rolling', 'roadmap summary', 1)"
            ),
            {"sm": str(summary), "c": str(conv), "u": str(tenant)},
        )
        await s.execute(
            text(
                "INSERT INTO conversation_summary_embeddings (summary_id, "
                "user_id, embedding_model, embedding_dimension, content_hash, "
                "embedding_vector) VALUES (:sm, :u, 'test', 384, 'h', "
                "CAST(:vec AS vector))"
            ),
            {"sm": str(summary), "u": str(tenant), "vec": _SEARCH_VECTOR_SQL},
        )
        await s.commit()
    return conv


async def test_conversation_search_isolation_under_rls() -> None:
    """M7: keyword + semantic search return only the acting tenant's threads."""
    dsn = os.environ["RLS_TEST_DSN"]
    engine = create_async_engine(dsn, poolclass=None)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    alice = uuid.uuid4()
    bob = uuid.uuid4()
    try:
        alice_conv = await _seed_searchable(maker, alice)
        bob_conv = await _seed_searchable(maker, bob)

        # Keyword: each tenant sees only their own matching conversation.
        async with maker() as s:
            await _set_tenant(s, alice)
            kw = await search_repo.keyword_search(
                s, user_id=alice, query="roadmap", limit=10
            )
            assert [row[0] for row in kw] == [alice_conv]

            sem = await search_repo.summary_semantic_search(
                s,
                user_id=alice,
                query_vector=_SEARCH_QUERY_VECTOR,
                embedding_model="test",
                limit=10,
            )
            assert [row[0] for row in sem] == [alice_conv]

        async with maker() as s:
            await _set_tenant(s, bob)
            kw = await search_repo.keyword_search(
                s, user_id=bob, query="roadmap", limit=10
            )
            assert [row[0] for row in kw] == [bob_conv]

        # Cross-tenant: under Alice's GUC, querying Bob's id returns nothing
        # (RLS hides Bob's rows AND the user_id filter excludes them).
        async with maker() as s:
            await _set_tenant(s, alice)
            kw = await search_repo.keyword_search(
                s, user_id=bob, query="roadmap", limit=10
            )
            assert kw == []
            sem = await search_repo.summary_semantic_search(
                s,
                user_id=bob,
                query_vector=_SEARCH_QUERY_VECTOR,
                embedding_model="test",
                limit=10,
            )
            assert sem == []
    finally:
        for tenant in (alice, bob):
            async with maker() as s:
                await _set_tenant(s, tenant)
                await s.execute(
                    text("DELETE FROM conversations WHERE user_id = :u"),
                    {"u": str(tenant)},
                )
                await s.execute(
                    text("DELETE FROM users WHERE id = :u"), {"u": str(tenant)}
                )
                await s.commit()
        await engine.dispose()
