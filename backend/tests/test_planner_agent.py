"""Planner Agent tests (Phase 3, M8) — grounded planning via the M7 seam."""

from __future__ import annotations

import uuid

from app.schemas.agents import AgentTask, ContextPack
from app.services.agents import handlers
from app.services.agents.manifests import PLANNER_AGENT_KEY
from app.services.llm.fake_provider import FakeLLMProvider


def _task(intent: str) -> AgentTask:
    return AgentTask(
        run_id=uuid.uuid4(),
        agent_key=PLANNER_AGENT_KEY,
        intent=intent,
        context_pack=ContextPack(
            goals=[
                {
                    "id": str(uuid.uuid4()),
                    "title": "Land an AI Engineer job",
                    "status": "active",
                    "priority": "high",
                    "progress_percentage": 20,
                    "target_date": "2026-07-01",
                }
            ]
        ),
    )


async def test_planner_agent_grounds_goals_and_uses_persona() -> None:
    llm = FakeLLMProvider(reply="Here is your 30-day plan.")
    result = await handlers.dispatch(_task("Create a 30-day roadmap"), llm=llm)
    assert result.output["reply"] == "Here is your 30-day plan."
    system = str(llm.calls[0]["system"])
    assert "Planner Agent" in system
    # The active goal flows in through the unified <knowledge> block.
    assert "Land an AI Engineer job" in system


async def test_planner_agent_handles_empty_pack() -> None:
    llm = FakeLLMProvider(reply="Let's define a goal first.")
    task = AgentTask(
        run_id=uuid.uuid4(),
        agent_key=PLANNER_AGENT_KEY,
        intent="plan my week",
        context_pack=ContextPack(),
    )
    result = await handlers.dispatch(task, llm=llm)
    assert result.output["reply"]
