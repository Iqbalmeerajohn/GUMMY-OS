"""Per-agent prompt builders (Phase 3, M8).

Each specialist owns a ``build_persona(message, knowledge) -> str`` that returns
the reasoning/formatting persona prepended to the shared grounded system prompt
(``memory.prompt_builder.build_prompt``). This is agent **isolation** (Rule #2):
identity and style live here; retrieval and grounding never do — those flow
through the M7 Unified Knowledge seam in the shared specialist handler.

``PERSONA_BUILDERS`` maps an agent key to its builder so the handler dispatch can
look one up without a hardcoded ``if`` ladder.
"""

from __future__ import annotations

from collections.abc import Callable

from app.services.agents.manifests import (
    AUTOMATION_AGENT_KEY,
    CAREER_AGENT_KEY,
    LEARNING_AGENT_KEY,
    MEMORY_AGENT_KEY,
    PLANNER_AGENT_KEY,
    RESEARCH_AGENT_KEY,
)
from app.services.agents.prompts import (
    automation_agent_prompt,
    career_agent_prompt,
    learning_agent_prompt,
    memory_agent_prompt,
    planner_agent_prompt,
    research_agent_prompt,
)

# Signature every persona builder implements.
PersonaBuilder = Callable[[str, str], str]

PERSONA_BUILDERS: dict[str, PersonaBuilder] = {
    AUTOMATION_AGENT_KEY: automation_agent_prompt.build_persona,
    CAREER_AGENT_KEY: career_agent_prompt.build_persona,
    LEARNING_AGENT_KEY: learning_agent_prompt.build_persona,
    PLANNER_AGENT_KEY: planner_agent_prompt.build_persona,
    MEMORY_AGENT_KEY: memory_agent_prompt.build_persona,
    RESEARCH_AGENT_KEY: research_agent_prompt.build_persona,
}
