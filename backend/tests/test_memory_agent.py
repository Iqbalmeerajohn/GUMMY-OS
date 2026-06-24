"""Memory Agent tests (Phase 3, M8) — strictly grounded recall via the M7 seam."""

from __future__ import annotations

import uuid

from app.schemas.agents import AgentTask, ContextPack
from app.services.agents import handlers
from app.services.agents.manifests import MEMORY_AGENT_KEY
from app.services.llm.fake_provider import FakeLLMProvider


def _task(intent: str) -> AgentTask:
    return AgentTask(
        run_id=uuid.uuid4(),
        agent_key=MEMORY_AGENT_KEY,
        intent=intent,
        context_pack=ContextPack(
            memories=[
                {
                    "content": "User lives in Singapore",
                    "category": "personal",
                    "score": 0.95,
                }
            ]
        ),
    )


async def test_memory_agent_grounds_and_uses_persona() -> None:
    llm = FakeLLMProvider(reply="Here's what I know about you.")
    result = await handlers.dispatch(_task("What do you know about me?"), llm=llm)
    assert result.output["reply"] == "Here's what I know about you."
    assert result.output["memories_used"] == 1
    system = str(llm.calls[0]["system"])
    assert "Memory Agent" in system
    assert "Singapore" in system


async def test_memory_agent_handles_empty_pack() -> None:
    llm = FakeLLMProvider(reply="I don't know much yet.")
    task = AgentTask(
        run_id=uuid.uuid4(),
        agent_key=MEMORY_AGENT_KEY,
        intent="what do you remember",
        context_pack=ContextPack(),
    )
    result = await handlers.dispatch(task, llm=llm)
    assert result.output["reply"]
    assert result.output["memories_used"] == 0
