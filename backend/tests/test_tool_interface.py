"""Tool Execution Interface tests (Phase 3, M6).

Proves: Green tools execute and are audited; a tool outside the manifest is
blocked; Yellow/Red calls return a pending handle and are **never executed**;
unknown tools are blocked; every path writes exactly one audit row; and the
``tool_invocations`` schema is registered as the migration creates it.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base
from app.models.enums import (
    MemoryCategory,
    PermissionTier,
    ToolDecision,
    ToolRunStatus,
)
from app.models.memory import Memory
from app.models.tool_invocation import ToolInvocation
from app.repositories import agent_run_repository as run_repo
from app.repositories import memory_repository as mem_repo
from app.repositories import tool_invocation_repository as audit_repo
from app.services.agents.manifests import RECALL_AGENT_KEY
from app.services.agents.tools import interface
from app.services.agents.tools.catalog import TOOL_CATALOG
from app.services.agents.tools.context import ToolContext
from app.services.embeddings.embedding_service import EmbeddingService
from app.services.embeddings.fake_provider import FakeEmbeddingProvider


async def _fake_search(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    query_vector: list[float],
    embedding_model: str,
    limit: int,
    include_archived: bool = False,
    category: MemoryCategory | None = None,
) -> list[tuple[Memory, float]]:
    items, _ = await mem_repo.list_memories(
        session, user_id=user_id, limit=limit, offset=0
    )
    return [(memory, 0.8) for memory in items]


def _context(
    session: AsyncSession, user_id: uuid.UUID
) -> ToolContext:
    return ToolContext(
        session=session,
        user_id=user_id,
        embedding_service=EmbeddingService(FakeEmbeddingProvider()),
    )


async def _run(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    run = await run_repo.create_run(session, user_id=user_id)
    return run.id


# ── schema sanity (migration 0015 mirror) ─────────────────────────────────────


def test_tool_invocations_table_registered() -> None:
    table = Base.metadata.tables["tool_invocations"]
    assert {
        "id",
        "user_id",
        "run_id",
        "agent_key",
        "tool_key",
        "args",
        "tier",
        "decision",
        "status",
        "decision_reason",
        "output_ref",
        "error",
        "cost_tokens",
        "cost_usd",
        "finished_at",
        "created_at",
    } <= set(table.columns.keys())
    assert {ix.name for ix in table.indexes} >= {
        "ix_tool_invocations_user_id",
        "ix_tool_invocations_run_id",
    }
    for constraint in table.constraints:
        if constraint.name is not None:
            assert len(str(constraint.name)) <= 63


def test_catalog_green_tools_have_executors() -> None:
    for spec in TOOL_CATALOG.values():
        if spec.tier == PermissionTier.GREEN:
            assert spec.executor is not None, spec.key
        else:
            # Phase 3 invariant: no non-Green executor exists at all.
            assert spec.executor is None, spec.key


# ── invoke paths ──────────────────────────────────────────────────────────────


async def test_green_memory_read_executes_and_audits(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.repositories.search_repository.search_similar_memories",
        _fake_search,
    )
    await mem_repo.create_memory(
        db_session,
        user_id=seed_user,
        category=MemoryCategory.CAREER,
        content="Qualcomm interview prep",
        importance_score=0.8,
        confidence_score=0.8,
    )
    run_id = await _run(db_session, seed_user)
    result = await interface.invoke(
        db_session,
        tool_key="memory_read",
        args={"query": "interview"},
        agent_key=RECALL_AGENT_KEY,
        run_id=run_id,
        user_id=seed_user,
        context=_context(db_session, seed_user),
    )
    assert result.decision == ToolDecision.ALLOWED
    assert result.status == ToolRunStatus.SUCCEEDED
    assert result.output is not None
    assert result.output["memories"][0]["content"] == (
        "Qualcomm interview prep"
    )
    rows = await audit_repo.list_for_run(
        db_session, run_id=run_id, user_id=seed_user
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.tool_key == "memory_read"
    assert row.tier == PermissionTier.GREEN
    assert row.decision == ToolDecision.ALLOWED
    assert row.status == ToolRunStatus.SUCCEEDED
    assert row.output_ref == {"memories": 1}


async def test_tool_not_in_manifest_blocked_and_audited(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    run_id = await _run(db_session, seed_user)
    # recall's manifest declares only memory_read.
    result = await interface.invoke(
        db_session,
        tool_key="web_search",
        args={"query": "anything"},
        agent_key=RECALL_AGENT_KEY,
        run_id=run_id,
        user_id=seed_user,
        context=_context(db_session, seed_user),
    )
    assert result.decision == ToolDecision.BLOCKED
    assert result.status == ToolRunStatus.NOT_EXECUTED
    assert result.output is None
    rows = await audit_repo.list_for_run(
        db_session, run_id=run_id, user_id=seed_user
    )
    assert [r.decision for r in rows] == [ToolDecision.BLOCKED]


async def test_yellow_red_never_execute(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Yellow/Red → pending handle; no executor can fire (none exists)."""
    from app.schemas.agents import AgentManifest
    from app.services.agents import registry as registry_module
    from app.services.agents.registry import AgentRegistry

    powerful = AgentManifest(
        key="powerful",
        display_name="Powerful",
        mission="Has risky tools.",
        ceiling=PermissionTier.RED,
        tools=("email_send", "social_publish"),
    )
    monkeypatch.setattr(
        registry_module, "_registry", AgentRegistry((powerful,))
    )

    run_id = await _run(db_session, seed_user)
    for tool_key, tier in (
        ("email_send", PermissionTier.YELLOW),
        ("social_publish", PermissionTier.RED),
    ):
        result = await interface.invoke(
            db_session,
            tool_key=tool_key,
            args={"to": "someone"},
            agent_key="powerful",
            run_id=run_id,
            user_id=seed_user,
            context=_context(db_session, seed_user),
        )
        assert result.tier == tier
        assert result.decision == ToolDecision.PENDING
        assert result.status == ToolRunStatus.NOT_EXECUTED
        assert result.output is None

    rows = await audit_repo.list_for_run(
        db_session, run_id=run_id, user_id=seed_user
    )
    assert len(rows) == 2
    assert all(r.status == ToolRunStatus.NOT_EXECUTED for r in rows)


async def test_yellow_with_standing_allowance_still_not_executed(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even policy-ALLOWED Yellow cannot run: no non-Green executor exists."""
    from app.schemas.agents import AgentManifest
    from app.services.agents import registry as registry_module
    from app.services.agents.registry import AgentRegistry

    powerful = AgentManifest(
        key="powerful",
        display_name="Powerful",
        mission="Has risky tools.",
        ceiling=PermissionTier.YELLOW,
        tools=("email_send",),
    )
    monkeypatch.setattr(
        registry_module, "_registry", AgentRegistry((powerful,))
    )
    run_id = await _run(db_session, seed_user)
    result = await interface.invoke(
        db_session,
        tool_key="email_send",
        args={},
        agent_key="powerful",
        run_id=run_id,
        user_id=seed_user,
        context=_context(db_session, seed_user),
        standing_allowances=frozenset({"email_send"}),
    )
    assert result.decision == ToolDecision.PENDING
    assert result.status == ToolRunStatus.NOT_EXECUTED


async def test_unknown_tool_blocked(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    run_id = await _run(db_session, seed_user)
    result = await interface.invoke(
        db_session,
        tool_key="teleport",
        args={},
        agent_key=RECALL_AGENT_KEY,
        run_id=run_id,
        user_id=seed_user,
        context=_context(db_session, seed_user),
    )
    assert result.decision == ToolDecision.BLOCKED
    assert result.tier == PermissionTier.RED  # unknown = maximal caution


async def test_green_failure_recorded(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    run_id = await _run(db_session, seed_user)
    # Empty query makes the executor raise; the failure is audited, not lost.
    result = await interface.invoke(
        db_session,
        tool_key="memory_read",
        args={"query": "   "},
        agent_key=RECALL_AGENT_KEY,
        run_id=run_id,
        user_id=seed_user,
        context=_context(db_session, seed_user),
    )
    assert result.decision == ToolDecision.ALLOWED
    assert result.status == ToolRunStatus.FAILED
    rows = (
        (await db_session.execute(select(ToolInvocation))).scalars().all()
    )
    assert rows[0].error is not None


async def test_web_search_delegates_to_search_seam(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.schemas.agents import AgentManifest
    from app.services.agents import registry as registry_module
    from app.services.agents.registry import AgentRegistry
    from app.services.search import SearchResult, get_provider, set_provider

    searcher = AgentManifest(
        key="searcher",
        display_name="Searcher",
        mission="Searches.",
        ceiling=PermissionTier.GREEN,
        tools=("web_search",),
    )
    monkeypatch.setattr(
        registry_module, "_registry", AgentRegistry((searcher,))
    )

    class _Stub:
        async def search(
            self, query: str, *, limit: int = 5
        ) -> list[SearchResult]:
            return [
                SearchResult(
                    title="Gummy OS",
                    url="https://example.com/gummy",
                    snippet="A personal AI OS.",
                    source="stub",
                )
            ]

    original = get_provider()
    set_provider(_Stub())
    try:
        run_id = await _run(db_session, seed_user)
        result = await interface.invoke(
            db_session,
            tool_key="web_search",
            args={"query": "gummy os"},
            agent_key="searcher",
            run_id=run_id,
            user_id=seed_user,
            context=_context(db_session, seed_user),
        )
    finally:
        set_provider(original)
    assert result.status == ToolRunStatus.SUCCEEDED
    # The tool delegates to the single search seam and flags results untrusted.
    assert result.output["untrusted"] is True
    assert result.output["results"][0]["url"] == "https://example.com/gummy"
