"""The general-purpose conversational agent (Phase 3, M4).

A pure ``AgentTask -> AgentResult`` function. Grounding is delegated to
``handlers.grounding``, the single implementation shared with the specialists —
so given the same packed inputs every agent produces an identical
``<knowledge>`` block and prompt, differing only by the persona a specialist
prepends. The general agent supplies no persona.
"""

from __future__ import annotations

from app.schemas.agents import AgentResult, AgentTask
from app.services.agents.handlers import grounding
from app.services.llm.base import LLMProvider


async def handle(task: AgentTask, *, llm: LLMProvider) -> AgentResult:
    """Ground a reply in the task's context pack and return it as a result."""
    return await grounding.handle(task, llm=llm)
