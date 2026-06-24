"""Research Agent tests (Phase 3, M8) — grounded analysis via the M7 seam."""

from __future__ import annotations

import uuid

from app.schemas.agents import AgentTask, ContextPack
from app.services.agents import handlers
from app.services.agents.manifests import RESEARCH_AGENT_KEY
from app.services.llm.fake_provider import FakeLLMProvider


def _task(intent: str) -> AgentTask:
    return AgentTask(
        run_id=uuid.uuid4(),
        agent_key=RESEARCH_AGENT_KEY,
        intent=intent,
        context_pack=ContextPack(
            memories=[
                {
                    "content": "User is deciding between AI and Data roles",
                    "category": "career",
                    "score": 0.7,
                }
            ]
        ),
    )


async def test_research_agent_grounds_and_uses_persona() -> None:
    llm = FakeLLMProvider(reply="Here is a side-by-side comparison.")
    result = await handlers.dispatch(
        _task("Compare AI Engineer vs Data Engineer"), llm=llm
    )
    assert result.output["reply"] == "Here is a side-by-side comparison."
    system = str(llm.calls[0]["system"])
    assert "Research Agent" in system
    assert "AI and Data roles" in system


async def test_research_agent_handles_empty_pack() -> None:
    llm = FakeLLMProvider(reply="Here is what I can analyze.")
    task = AgentTask(
        run_id=uuid.uuid4(),
        agent_key=RESEARCH_AGENT_KEY,
        intent="research the job market",
        context_pack=ContextPack(),
    )
    result = await handlers.dispatch(task, llm=llm)
    assert result.output["reply"]
