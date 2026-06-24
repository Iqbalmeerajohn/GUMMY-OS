"""Multi-Agent Workforce endpoints (``/api/v1/agents``) — Phase 3, M8.

Read-only introspection over the agent layer:

* ``GET /agents`` — the catalog of available agents (for the workspace selector);
* ``GET /agents/diagnostics`` — trace which agent the deterministic Router would
  pick for a query, and why, without executing it.

Both build on the same ``router.score_agents`` the orchestrator uses, so the
diagnostics explanation always matches live routing.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserId
from app.core.exceptions import AppError
from app.schemas.agent_diagnostics import (
    AgentDiagnosticsResponse,
    AgentInfo,
)
from app.services.agents import router as agent_router
from app.services.agents.manifests import (
    GENERAL_AGENT_KEY,
    SPECIALIST_AGENT_KEYS,
)
from app.services.agents.registry import get_registry

router = APIRouter(prefix="/agents", tags=["agents"])

# The agents the workspace selector advertises: the user-facing specialists plus
# the General fallback. The internal ``recall`` pipeline head is not a selectable
# agent, so it is intentionally excluded.
_LISTED_AGENT_KEYS: tuple[str, ...] = (GENERAL_AGENT_KEY, *SPECIALIST_AGENT_KEYS)


def _available_agents() -> list[AgentInfo]:
    """The catalog of selectable agents, from the in-code registry."""
    registry = get_registry()
    registered = registry.keys()
    infos: list[AgentInfo] = []
    for key in _LISTED_AGENT_KEYS:
        if key not in registered:
            continue
        manifest = registry.get(key)
        infos.append(
            AgentInfo(
                name=manifest.key,
                display_name=manifest.display_name,
                description=manifest.mission,
                keywords=list(manifest.keywords),
            )
        )
    return infos


@router.get(
    "",
    response_model=list[AgentInfo],
    summary="List the available agents (for the workspace selector)",
)
async def list_agents(user_id: CurrentUserId) -> list[AgentInfo]:
    """Return the selectable agents: General + the five M8 specialists."""
    return _available_agents()


@router.get(
    "/diagnostics",
    response_model=AgentDiagnosticsResponse,
    summary="Explain which agent the Router would pick for a query",
)
async def agent_diagnostics(
    user_id: CurrentUserId,
    q: Annotated[str, Query(min_length=1, max_length=1000)],
) -> AgentDiagnosticsResponse:
    """Score a query through the deterministic Router and report the decision.

    Read-only and side-effect-free: no agent runs, nothing is persisted. Uses the
    same ``score_agents`` the orchestrator routes on, so the explanation matches
    production routing exactly.
    """
    query = q.strip()
    if not query:
        raise AppError(
            "query must not be empty or whitespace",
            code="empty_query",
            status_code=422,
        )

    decision = agent_router.score_agents(query, get_registry())
    return AgentDiagnosticsResponse(
        query=query,
        selected_agent=decision.steps[-1].agent_key,
        confidence=decision.confidence,
        reason=decision.rationale,
        available_agents=_available_agents(),
    )
