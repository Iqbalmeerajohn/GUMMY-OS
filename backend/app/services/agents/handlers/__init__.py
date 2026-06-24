"""Agent handlers — pure ``AgentTask -> AgentResult`` functions.

Each built-in agent registers a manifest (manifests.py) and implements one
handler here. Handlers never persist, never commit, and never execute
actions; they reason over the task's context pack and return proposals
(PHASE3_PLAN.md §9/§12). ``dispatch`` is the orchestrator's single door to a
handler — adding an agent = manifest + handler + an entry here.
"""

from __future__ import annotations

from app.schemas.agents import AgentResult, AgentTask
from app.services.agents.handlers import (
    general_agent,
    recall_agent,
    specialist_agent,
)
from app.services.agents.manifests import (
    GENERAL_AGENT_KEY,
    RECALL_AGENT_KEY,
)
from app.services.agents.prompts import PERSONA_BUILDERS
from app.services.llm.base import LLMProvider


class UnknownAgentError(KeyError):
    """No handler is registered for the requested agent key."""


async def dispatch(
    task: AgentTask, *, llm: LLMProvider
) -> AgentResult:
    """Invoke the handler registered for ``task.agent_key``."""
    if task.agent_key == GENERAL_AGENT_KEY:
        return await general_agent.handle(task, llm=llm)
    if task.agent_key == RECALL_AGENT_KEY:
        return await recall_agent.handle(task)
    # The five M8 specialists share one handler, differing only by persona.
    persona_fn = PERSONA_BUILDERS.get(task.agent_key)
    if persona_fn is not None:
        return await specialist_agent.handle(task, llm=llm, persona_fn=persona_fn)
    raise UnknownAgentError(task.agent_key)
