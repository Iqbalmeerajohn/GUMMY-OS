"""Repository tests for the Phase 3 agent-framework tables (M2).

Pure persistence behavior on in-memory SQLite: CRUD, tenant scoping, seq
assignment + ordering, cost accumulation, the enabled filter, and
global-vs-user catalog visibility. RLS itself is proven by the gated
Postgres suite; here the repositories must scope every query by user_id.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.enums import (
    AgentMessageRole,
    PermissionTier,
    RunStatus,
    RunTrigger,
    StepStatus,
)
from app.models.user import User
from app.repositories import (
    agent_message_repository,
    agent_repository,
    agent_run_repository,
    agent_step_repository,
)


async def _second_user(session: AsyncSession) -> uuid.UUID:
    other = User(email=f"other-{uuid.uuid4().hex[:8]}@example.com")
    session.add(other)
    await session.commit()
    return other.id


# ── agent_repository ──────────────────────────────────────────────────────────


async def test_upsert_catalog_inserts_global_row(
    db_session: AsyncSession,
) -> None:
    agent = await agent_repository.upsert_catalog(
        db_session,
        key="general",
        display_name="General",
        mission="Answer anything.",
        ceiling=PermissionTier.GREEN,
        tool_manifest=["memory_read"],
    )
    assert agent.user_id is None
    assert agent.enabled is True
    assert agent.tool_manifest == ["memory_read"]
    fetched = await agent_repository.get_by_key(db_session, "general")
    assert fetched is not None
    assert fetched.id == agent.id


async def test_upsert_catalog_refreshes_but_preserves_enabled(
    db_session: AsyncSession,
) -> None:
    agent = await agent_repository.upsert_catalog(
        db_session,
        key="general",
        display_name="General",
        mission="Old mission.",
        ceiling=PermissionTier.GREEN,
        tool_manifest=[],
    )
    agent.enabled = False  # runtime state: manually disabled
    await db_session.flush()

    again = await agent_repository.upsert_catalog(
        db_session,
        key="general",
        display_name="General v2",
        mission="New mission.",
        ceiling=PermissionTier.YELLOW,
        tool_manifest=["web_search"],
        model_tier="fast",
    )
    assert again.id == agent.id  # same row, no duplicate
    assert again.display_name == "General v2"
    assert again.ceiling == PermissionTier.YELLOW
    assert again.tool_manifest == ["web_search"]
    assert again.model_tier == "fast"
    assert again.enabled is False  # preserved across reseed


async def test_list_enabled_visibility(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    other = await _second_user(db_session)
    await agent_repository.upsert_catalog(
        db_session,
        key="general",
        display_name="General",
        mission="m",
        ceiling=PermissionTier.GREEN,
        tool_manifest=[],
    )
    disabled = await agent_repository.upsert_catalog(
        db_session,
        key="disabled",
        display_name="Disabled",
        mission="m",
        ceiling=PermissionTier.GREEN,
        tool_manifest=[],
    )
    disabled.enabled = False
    # A user-defined agent for `other` (future seam, exercised now).
    db_session.add(
        Agent(
            user_id=other,
            key="other-private",
            display_name="Private",
            mission="m",
            tool_manifest=[],
        )
    )
    await db_session.flush()

    mine = await agent_repository.list_enabled(db_session, user_id=seed_user)
    assert [a.key for a in mine] == ["general"]

    theirs = await agent_repository.list_enabled(db_session, user_id=other)
    assert [a.key for a in theirs] == ["general", "other-private"]

    seed_view = await agent_repository.list_enabled(db_session)
    assert [a.key for a in seed_view] == ["general"]


# ── agent_run_repository ──────────────────────────────────────────────────────


async def test_create_run_defaults(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    run = await agent_run_repository.create_run(db_session, user_id=seed_user)
    assert run.id is not None
    assert run.status == RunStatus.RUNNING
    assert run.trigger == RunTrigger.CHAT
    assert run.conversation_id is None
    assert run.cost_tokens == 0
    assert run.finished_at is None


async def test_get_run_is_tenant_scoped(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    other = await _second_user(db_session)
    run = await agent_run_repository.create_run(db_session, user_id=seed_user)
    assert (
        await agent_run_repository.get_run(db_session, run_id=run.id, user_id=seed_user)
    ) is not None
    assert (
        await agent_run_repository.get_run(db_session, run_id=run.id, user_id=other)
    ) is None


async def test_set_status_stamps_finished_at(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    run = await agent_run_repository.create_run(db_session, user_id=seed_user)
    await agent_run_repository.set_status(
        db_session, run, status=RunStatus.FAILED, error="handler exploded"
    )
    assert run.status == RunStatus.FAILED
    assert run.error == "handler exploded"
    assert run.finished_at is not None


async def test_add_cost_accumulates(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    run = await agent_run_repository.create_run(db_session, user_id=seed_user)
    await agent_run_repository.add_cost(db_session, run, tokens=100, usd=0.001)
    await agent_run_repository.add_cost(
        db_session, run, tokens=50, usd=Decimal("0.0005")
    )
    assert run.cost_tokens == 150
    assert run.cost_usd == Decimal("0.0015")


async def test_list_for_conversation_newest_first(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    from app.models.conversation import Conversation

    conv = Conversation(user_id=seed_user)
    db_session.add(conv)
    await db_session.flush()
    first = await agent_run_repository.create_run(
        db_session, user_id=seed_user, conversation_id=conv.id
    )
    second = await agent_run_repository.create_run(
        db_session, user_id=seed_user, conversation_id=conv.id
    )
    # SQLite second-resolution timestamps collide; force distinct ordering.
    from datetime import UTC, datetime, timedelta

    first.created_at = datetime.now(UTC) - timedelta(seconds=10)
    await db_session.flush()
    runs = await agent_run_repository.list_for_conversation(
        db_session, conversation_id=conv.id, user_id=seed_user, limit=10
    )
    assert [r.id for r in runs] == [second.id, first.id]


# ── agent_step_repository ─────────────────────────────────────────────────────


async def test_append_step_assigns_monotonic_seq(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    run = await agent_run_repository.create_run(db_session, user_id=seed_user)
    other_run = await agent_run_repository.create_run(db_session, user_id=seed_user)
    s1 = await agent_step_repository.append_step(
        db_session, run_id=run.id, user_id=seed_user, agent_key="general"
    )
    s2 = await agent_step_repository.append_step(
        db_session,
        run_id=run.id,
        user_id=seed_user,
        agent_key="recall",
        input={"intent": "x"},
    )
    s_other = await agent_step_repository.append_step(
        db_session, run_id=other_run.id, user_id=seed_user, agent_key="general"
    )
    assert (s1.seq, s2.seq) == (1, 2)
    assert s_other.seq == 1  # per-run, not global
    assert s1.status == StepStatus.RUNNING
    assert s2.input == {"intent": "x"}


async def test_list_steps_for_run_ordered_and_scoped(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    other = await _second_user(db_session)
    run = await agent_run_repository.create_run(db_session, user_id=seed_user)
    for key in ("a", "b", "c"):
        await agent_step_repository.append_step(
            db_session, run_id=run.id, user_id=seed_user, agent_key=key
        )
    steps = await agent_step_repository.list_for_run(
        db_session, run_id=run.id, user_id=seed_user
    )
    assert [s.agent_key for s in steps] == ["a", "b", "c"]
    foreign = await agent_step_repository.list_for_run(
        db_session, run_id=run.id, user_id=other
    )
    assert foreign == []


# ── agent_message_repository ──────────────────────────────────────────────────


async def test_append_message_assigns_seq_and_lists_in_order(
    db_session: AsyncSession, seed_user: uuid.UUID
) -> None:
    other = await _second_user(db_session)
    run = await agent_run_repository.create_run(db_session, user_id=seed_user)
    m1 = await agent_message_repository.append_message(
        db_session,
        run_id=run.id,
        user_id=seed_user,
        from_agent="orchestrator",
        to_agent="general",
        role=AgentMessageRole.TASK,
        payload={"intent": "hello"},
    )
    m2 = await agent_message_repository.append_message(
        db_session,
        run_id=run.id,
        user_id=seed_user,
        from_agent="general",
        to_agent=None,
        role=AgentMessageRole.RESULT,
        payload={"output": "hi"},
    )
    assert (m1.seq, m2.seq) == (1, 2)
    hops = await agent_message_repository.list_for_run(
        db_session, run_id=run.id, user_id=seed_user
    )
    assert [(h.from_agent, h.role) for h in hops] == [
        ("orchestrator", AgentMessageRole.TASK),
        ("general", AgentMessageRole.RESULT),
    ]
    foreign = await agent_message_repository.list_for_run(
        db_session, run_id=run.id, user_id=other
    )
    assert foreign == []
