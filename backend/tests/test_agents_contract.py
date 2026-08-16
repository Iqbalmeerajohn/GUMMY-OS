"""Contract-type tests for the Agent Framework (Phase 3, M1).

The AgentTask/AgentResult contract is the framework's stable heart: these
tests pin its defaults, validation, and round-trip serialization so later
milestones can't drift it accidentally.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.models.enums import PermissionTier, PlanShape
from app.schemas.agents import (
    AgentManifest,
    AgentResult,
    AgentTask,
    ContextPack,
    CostInfo,
    OrchestrationResult,
    RouteStep,
    RoutingDecision,
)


def test_agent_manifest_defaults_and_frozen() -> None:
    manifest = AgentManifest(
        key="general",
        display_name="General",
        mission="Answer anything using memory + context.",
    )
    assert manifest.ceiling == PermissionTier.GREEN
    assert manifest.tools == ()
    assert manifest.keywords == ()
    assert manifest.enabled is True
    with pytest.raises(ValidationError):
        manifest.key = "other"  # frozen


def test_agent_manifest_rejects_invalid() -> None:
    with pytest.raises(ValidationError):
        AgentManifest(key="", display_name="X", mission="m")
    with pytest.raises(ValidationError):
        AgentManifest(key="k" * 65, display_name="X", mission="m")


def test_agent_task_defaults() -> None:
    task = AgentTask(run_id=uuid.uuid4(), agent_key="general", intent="hello")
    assert task.inputs == {}
    assert task.context_pack == ContextPack()
    assert task.permission_scope == PermissionTier.GREEN


def test_agent_task_round_trip() -> None:
    task = AgentTask(
        run_id=uuid.uuid4(),
        agent_key="general",
        intent="summarize",
        inputs={"text": "hi"},
        context_pack=ContextPack(
            memories=[{"content": "fact"}],
            history=[{"role": "user", "content": "hi"}],
            summary="prior summary",
        ),
        permission_scope=PermissionTier.GREEN,
    )
    restored = AgentTask.model_validate(task.model_dump())
    assert restored == task
    # JSON round-trip too (run_id serializes as str).
    restored_json = AgentTask.model_validate_json(task.model_dump_json())
    assert restored_json == task


def test_agent_result_defaults_and_round_trip() -> None:
    result = AgentResult(output={"reply": "hello"})
    assert result.proposed_actions == []
    assert result.proposed_memories == []
    assert result.citations == []
    assert result.next_suggestions == []
    assert result.cost == CostInfo(tokens=0, usd=0.0)
    restored = AgentResult.model_validate_json(result.model_dump_json())
    assert restored == result


def test_cost_info_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        CostInfo(tokens=-1)
    with pytest.raises(ValidationError):
        CostInfo(usd=-0.01)


def test_routing_decision_defaults_and_bounds() -> None:
    decision = RoutingDecision()
    assert decision.plan_shape == PlanShape.SINGLE
    assert decision.steps == []
    assert decision.confidence == 0.0
    decision = RoutingDecision(
        plan_shape=PlanShape.PIPELINE,
        steps=[RouteStep(agent_key="recall"), RouteStep(agent_key="general")],
        rationale="keyword match",
        confidence=0.9,
    )
    assert [s.agent_key for s in decision.steps] == ["recall", "general"]
    with pytest.raises(ValidationError):
        RoutingDecision(confidence=1.5)
    with pytest.raises(ValidationError):
        RoutingDecision(confidence=-0.1)


def test_orchestration_result_reply_shape() -> None:
    result = OrchestrationResult(reply="Here you go.")
    assert result.run_id is None
    assert result.message_metadata is None
    assert result.cost.tokens == 0
    run_id = uuid.uuid4()
    full = OrchestrationResult(
        reply="Done.",
        run_id=run_id,
        proposed_memories=[{"content": "durable fact"}],
        citations=[{"memory_id": str(uuid.uuid4())}],
        cost=CostInfo(tokens=123, usd=0.0042),
        message_metadata={"agent_key": "general"},
    )
    restored = OrchestrationResult.model_validate_json(full.model_dump_json())
    assert restored == full
