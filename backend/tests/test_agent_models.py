"""Schema/metadata tests for the Phase 3 Agent Framework tables (M1).

Mirrors test_conversation_models.py: asserts the new tables, columns, indexes,
constraints, enums, and relationship wiring are registered on Base.metadata
exactly as migrations 0012–0014 create them — and that Phase 1/2 models are
untouched.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.base import Base
from app.models import (
    Agent,
    AgentMessage,
    AgentMessageRole,
    AgentRun,
    AgentStep,
    Conversation,
    PermissionTier,
    PlanShape,
    RunStatus,
    RunTrigger,
    StepStatus,
    User,
)

_PHASE3_TABLES = {
    "agents",
    "agent_runs",
    "agent_steps",
    "agent_messages",
}


def test_phase3_tables_registered() -> None:
    assert set(Base.metadata.tables) >= _PHASE3_TABLES


def test_agent_columns() -> None:
    cols = set(Base.metadata.tables["agents"].columns.keys())
    assert {
        "id",
        "user_id",
        "key",
        "display_name",
        "mission",
        "ceiling",
        "tool_manifest",
        "model_tier",
        "enabled",
        "created_at",
        "updated_at",
    } <= cols


def test_agent_user_id_nullable_for_global_rows() -> None:
    table = Base.metadata.tables["agents"]
    assert table.columns["user_id"].nullable is True
    assert table.columns["key"].nullable is False


def test_agent_key_unique_constraint() -> None:
    table = Base.metadata.tables["agents"]
    names = {c.name for c in table.constraints}
    assert "uq_agents_key" in names


def test_agent_run_columns() -> None:
    cols = set(Base.metadata.tables["agent_runs"].columns.keys())
    assert {
        "id",
        "user_id",
        "conversation_id",
        "trigger",
        "route_plan",
        "status",
        "error",
        "cost_tokens",
        "cost_usd",
        "finished_at",
        "created_at",
        "updated_at",
    } <= cols


def test_agent_step_columns() -> None:
    cols = set(Base.metadata.tables["agent_steps"].columns.keys())
    assert {
        "id",
        "run_id",
        "user_id",
        "agent_key",
        "seq",
        "status",
        "input",
        "output",
        "error",
        "cost_tokens",
        "cost_usd",
        "finished_at",
        "created_at",
        "updated_at",
    } <= cols


def test_agent_message_columns() -> None:
    cols = set(Base.metadata.tables["agent_messages"].columns.keys())
    assert {
        "id",
        "run_id",
        "user_id",
        "from_agent",
        "to_agent",
        "role",
        "payload",
        "seq",
        "created_at",
    } <= cols


def test_seq_unique_constraints() -> None:
    steps = {c.name for c in Base.metadata.tables["agent_steps"].constraints}
    assert "uq_agent_steps_run_id_seq" in steps
    msgs = {
        c.name for c in Base.metadata.tables["agent_messages"].constraints
    }
    assert "uq_agent_messages_run_id_seq" in msgs


def test_denormalized_user_id_everywhere() -> None:
    # Direct-column RLS requires user_id on every Phase 3 table.
    for name in _PHASE3_TABLES:
        assert "user_id" in Base.metadata.tables[name].columns, name


def test_phase3_indexes_present() -> None:
    expected = {
        "agents": {"ix_agents_user_id"},
        "agent_runs": {
            "ix_agent_runs_user_id",
            "ix_agent_runs_conversation_id",
            "ix_agent_runs_user_id_created_at",
        },
        "agent_steps": {"ix_agent_steps_run_id", "ix_agent_steps_user_id"},
        "agent_messages": {
            "ix_agent_messages_run_id",
            "ix_agent_messages_user_id",
        },
    }
    for table, names in expected.items():
        actual = {ix.name for ix in Base.metadata.tables[table].indexes}
        assert names <= actual, table


def test_fk_wiring() -> None:
    def fk_targets(table: str) -> dict[str, str]:
        return {
            fk.parent.name: fk.column.table.name
            for fk in Base.metadata.tables[table].foreign_keys
        }

    assert fk_targets("agents")["user_id"] == "users"
    runs = fk_targets("agent_runs")
    assert runs["user_id"] == "users"
    assert runs["conversation_id"] == "conversations"
    steps = fk_targets("agent_steps")
    assert steps["run_id"] == "agent_runs"
    assert steps["user_id"] == "users"
    msgs = fk_targets("agent_messages")
    assert msgs["run_id"] == "agent_runs"
    assert msgs["user_id"] == "users"


def test_run_conversation_fk_set_null() -> None:
    # The audit trail must survive thread deletion.
    fks = {
        fk.parent.name: fk
        for fk in Base.metadata.tables["agent_runs"].foreign_keys
    }
    assert fks["conversation_id"].ondelete == "SET NULL"


def test_relationship_wiring() -> None:
    assert AgentRun.steps.property.mapper.class_ is AgentStep
    assert AgentRun.messages.property.mapper.class_ is AgentMessage
    assert AgentStep.run.property.mapper.class_ is AgentRun
    assert AgentMessage.run.property.mapper.class_ is AgentRun


def test_phase3_enum_values() -> None:
    assert {t.value for t in PermissionTier} == {"green", "yellow", "red"}
    assert {t.value for t in RunTrigger} == {"chat", "scheduler"}
    assert {s.value for s in RunStatus} == {"running", "succeeded", "failed"}
    assert {s.value for s in StepStatus} == {
        "running",
        "succeeded",
        "failed",
        "skipped",
    }
    assert {r.value for r in AgentMessageRole} == {"task", "result", "error"}
    assert {p.value for p in PlanShape} == {"single", "pipeline", "parallel"}


def test_all_identifier_names_within_postgres_limit() -> None:
    # Postgres truncates identifiers > 63 chars (the Phase 2 M1 lesson).
    for name in _PHASE3_TABLES:
        table = Base.metadata.tables[name]
        for constraint in table.constraints:
            if constraint.name is not None:
                assert len(str(constraint.name)) <= 63, constraint.name
        for index in table.indexes:
            assert len(str(index.name)) <= 63, index.name


def test_phase1_and_phase2_models_untouched() -> None:
    # FK-only links keep the frozen models frozen: no Phase 3 relationships
    # were added to User or Conversation.
    assert not hasattr(User, "agents")
    assert not hasattr(User, "agent_runs")
    assert not hasattr(Conversation, "agent_runs")


async def test_phase3_tables_create_on_sqlite(
    sessionmaker_fixture: async_sessionmaker[AsyncSession],
) -> None:
    """create_all built the Phase 3 tables; a full ORM chain round-trips."""
    async with sessionmaker_fixture() as session:
        user = User(email="agent-models@example.com")
        session.add(user)
        await session.flush()

        agent = Agent(
            key="general",
            display_name="General",
            mission="Answer anything.",
            tool_manifest=[],
        )
        run = AgentRun(user_id=user.id, route_plan={"shape": "single"})
        session.add_all([agent, run])
        await session.flush()

        step = AgentStep(
            run_id=run.id,
            user_id=user.id,
            agent_key="general",
            seq=1,
            input={"intent": "hello"},
        )
        message = AgentMessage(
            run_id=run.id,
            user_id=user.id,
            from_agent="orchestrator",
            to_agent="general",
            role=AgentMessageRole.TASK,
            payload={"intent": "hello"},
            seq=1,
        )
        session.add_all([step, message])
        await session.commit()

        await session.refresh(run)
        assert run.status == RunStatus.RUNNING  # server/python default
        assert run.trigger == RunTrigger.CHAT
        loaded = await session.get(AgentStep, step.id)
        assert loaded is not None
        assert loaded.input == {"intent": "hello"}
        assert agent.ceiling == PermissionTier.GREEN
