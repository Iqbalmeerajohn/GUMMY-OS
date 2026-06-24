"""Career Agent tests (Phase 3, M8).

Proves the specialist grounds through the M7 unified-knowledge seam (the packed
context, no direct retrieval — the handler takes no DB session), prepends its
persona to the system prompt, and returns a reply.
"""

from __future__ import annotations

import uuid

from app.schemas.agents import AgentTask, ContextPack
from app.services.agents import handlers
from app.services.agents.manifests import CAREER_AGENT_KEY
from app.services.llm.fake_provider import FakeLLMProvider


def _task(intent: str) -> AgentTask:
    return AgentTask(
        run_id=uuid.uuid4(),
        agent_key=CAREER_AGENT_KEY,
        intent=intent,
        context_pack=ContextPack(
            memories=[
                {
                    "content": "User is targeting an AI Engineer role",
                    "category": "career",
                    "score": 0.9,
                }
            ]
        ),
    )


async def test_career_agent_grounds_and_uses_persona() -> None:
    llm = FakeLLMProvider(reply="Here are roles to target.")
    result = await handlers.dispatch(
        _task("What jobs should I apply for?"), llm=llm
    )
    assert result.output["reply"] == "Here are roles to target."
    system = str(llm.calls[0]["system"])
    # Persona present (agent isolation) …
    assert "Career Agent" in system
    # … and the packed memory is grounded via the M7 <knowledge> block.
    assert "AI Engineer role" in system


async def test_career_agent_handles_empty_pack() -> None:
    llm = FakeLLMProvider(reply="I don't have your resume yet.")
    task = AgentTask(
        run_id=uuid.uuid4(),
        agent_key=CAREER_AGENT_KEY,
        intent="review my resume",
        context_pack=ContextPack(),
    )
    result = await handlers.dispatch(task, llm=llm)
    assert result.output["reply"]
    assert result.output["memories_used"] == 0
