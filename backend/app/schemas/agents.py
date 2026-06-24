"""Typed contracts for the Agent Framework (Phase 3, M1).

The one contract every agent implements: a handler is a pure function of
``AgentTask -> AgentResult``; the Orchestrator returns an
``OrchestrationResult`` shaped like the reply payload ``run_turn`` already
persists. Pure Pydantic — zero runtime wiring in M1 (see PHASE3_PLAN.md §9).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PermissionTier, PlanShape


class AgentManifest(BaseModel):
    """A code-defined agent declaration (the Registry's source of truth).

    The DB ``agents`` row carries runtime state (``enabled``); the manifest
    carries identity, capability, and the routing descriptors the Router
    consumes (PHASE3_PLAN.md §5).
    """

    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    mission: str = Field(min_length=1)
    ceiling: PermissionTier = PermissionTier.GREEN
    # Allowed tool keys; the Tool Interface enforces membership (M6).
    tools: tuple[str, ...] = ()
    # Routing descriptors: keyword hints the rules-first Router matches (M5).
    keywords: tuple[str, ...] = ()
    # Deterministic tie-break when two specialists score equally on keywords
    # (higher wins); 0 for the general/recall agents (M8).
    priority: int = 0
    model_tier: str | None = None
    enabled: bool = True


class ContextPack(BaseModel):
    """The token-budgeted context an agent receives (PHASE3_PLAN.md §8)."""

    memories: list[dict] = Field(default_factory=list)
    history: list[dict] = Field(default_factory=list)
    summary: str | None = None
    goals: list[dict] = Field(default_factory=list)
    tasks: list[dict] = Field(default_factory=list)
    # Uploaded-file *metadata* the agent can see (M6) — filename / type /
    # processing status only, never file content. Agent file-selection logic
    # builds on this seam in a later phase.
    files: list[dict] = Field(default_factory=list)
    # File Intelligence (M6.5): retrieved file *content* for grounding — an
    # ``{inventory, excerpts}`` dict (or ``None``). Populated when a file is
    # attached or the query matches uploaded documents; rendered into the
    # prompt's ``<files>`` block by the handler.
    file_context: dict | None = None
    # Prior agent outputs within this run (pipeline hand-off scratchpad).
    scratch: list[dict] = Field(default_factory=list)


class AgentTask(BaseModel):
    """The typed unit of work the Orchestrator dispatches to one agent."""

    run_id: uuid.UUID
    agent_key: str
    intent: str
    inputs: dict = Field(default_factory=dict)
    context_pack: ContextPack = Field(default_factory=ContextPack)
    # Least-privilege scope for this dispatch; never above the agent's ceiling.
    permission_scope: PermissionTier = PermissionTier.GREEN


class CostInfo(BaseModel):
    """Token + dollar cost of an agent invocation or a whole orchestration."""

    tokens: int = Field(default=0, ge=0)
    usd: float = Field(default=0.0, ge=0.0)


class AgentResult(BaseModel):
    """What every agent handler returns. Proposals only — agents never
    execute actions or persist memories themselves (PHASE3_PLAN.md §9/§12)."""

    output: dict = Field(default_factory=dict)
    proposed_actions: list[dict] = Field(default_factory=list)
    proposed_memories: list[dict] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    cost: CostInfo = Field(default_factory=CostInfo)
    next_suggestions: list[str] = Field(default_factory=list)


class RouteStep(BaseModel):
    """One step of a routing plan: which agent, with what (sub-)intent."""

    agent_key: str
    intent: str | None = None


class RoutingDecision(BaseModel):
    """The Router's verdict: who runs, in what shape, and why (§6)."""

    plan_shape: PlanShape = PlanShape.SINGLE
    steps: list[RouteStep] = Field(default_factory=list)
    rationale: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # The specialist keywords that fired for the winning agent (A4: routing
    # explanation). Empty for the general/recall defaults (no keyword match).
    matched_keywords: list[str] = Field(default_factory=list)


class OrchestrationResult(BaseModel):
    """The reply-shaped payload the Orchestrator hands back to ``run_turn``
    (it persists the assistant message exactly as the Phase 2 path does)."""

    reply: str
    run_id: uuid.UUID | None = None
    proposed_actions: list[dict] = Field(default_factory=list)
    proposed_memories: list[dict] = Field(default_factory=list)
    citations: list[dict] = Field(default_factory=list)
    cost: CostInfo = Field(default_factory=CostInfo)
    message_metadata: dict | None = None
    # Reply accounting `run_turn` persists on the assistant message (the same
    # fields GeneratedReply carries on the legacy path).
    model: str = ""
    memories_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
