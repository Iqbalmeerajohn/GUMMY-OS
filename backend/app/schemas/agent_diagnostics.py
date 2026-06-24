"""Schemas for the agent routing diagnostics endpoint (Phase 3, M8).

Answers, for a given query, which specialist the deterministic Router would pick
and why — without executing the agent. Read-only: the same explainable decision
the orchestrator acts on, surfaced for debugging and demos.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AgentInfo(BaseModel):
    """One available agent, as advertised to the router and the UI."""

    name: str
    display_name: str
    description: str
    keywords: list[str] = Field(default_factory=list)


class AgentDiagnosticsResponse(BaseModel):
    """The Router's decision for a query plus the catalog it chose from."""

    query: str
    selected_agent: str
    confidence: float
    reason: str
    # A4 routing explanation: the keywords that fired and a human-readable
    # reason. ``routing_reason`` mirrors ``reason`` under the brief's field name.
    matched_keywords: list[str] = Field(default_factory=list)
    routing_reason: str = ""
    available_agents: list[AgentInfo] = Field(default_factory=list)
