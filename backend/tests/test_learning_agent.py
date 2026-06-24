"""Learning Agent tests (Phase 3, M8) — grounded teaching via the M7 seam."""

from __future__ import annotations

import uuid

from app.schemas.agents import AgentTask, ContextPack
from app.services.agents import handlers
from app.services.agents.manifests import LEARNING_AGENT_KEY
from app.services.llm.fake_provider import FakeLLMProvider


def _task(intent: str) -> AgentTask:
    return AgentTask(
        run_id=uuid.uuid4(),
        agent_key=LEARNING_AGENT_KEY,
        intent=intent,
        context_pack=ContextPack(
            memories=[
                {
                    "content": "User has a strong Python background",
                    "category": "skill",
                    "score": 0.8,
                }
            ]
        ),
    )


async def test_learning_agent_grounds_and_uses_persona() -> None:
    llm = FakeLLMProvider(reply="Let's start with attention.")
    result = await handlers.dispatch(_task("Teach me transformers"), llm=llm)
    assert result.output["reply"] == "Let's start with attention."
    system = str(llm.calls[0]["system"])
    assert "Learning Agent" in system
    assert "Python background" in system


async def test_learning_agent_handles_empty_pack() -> None:
    llm = FakeLLMProvider(reply="Here is a roadmap.")
    task = AgentTask(
        run_id=uuid.uuid4(),
        agent_key=LEARNING_AGENT_KEY,
        intent="roadmap for deep learning",
        context_pack=ContextPack(),
    )
    result = await handlers.dispatch(task, llm=llm)
    assert result.output["reply"]
