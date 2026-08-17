"""Shared handler for the M8 specialist agents (Career/Learning/Planner/
Memory/Research).

One ``AgentTask -> AgentResult`` function for all five: grounding, ranking, and
prompt assembly are ``handlers.grounding`` — identical to the general agent's —
and per-agent identity is supplied entirely by ``persona_fn`` (from
``services/agents/prompts``). No specialist retrieves on its own (Rule #1), and
execution is not duplicated per agent: one handler, five personas.
"""

from __future__ import annotations

from app.schemas.agents import AgentResult, AgentTask
from app.services.agents.handlers import grounding
from app.services.agents.prompts import PersonaBuilder
from app.services.llm.base import LLMProvider


async def handle(
    task: AgentTask, *, llm: LLMProvider, persona_fn: PersonaBuilder
) -> AgentResult:
    """Ground a reply in the task's context pack, in a specialist's voice."""
    return await grounding.handle(task, llm=llm, persona_fn=persona_fn)
