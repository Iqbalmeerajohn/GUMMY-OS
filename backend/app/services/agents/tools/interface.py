"""The Tool Execution Interface — manifest check + policy gate + audit.

``invoke`` is the **only** door through which an agent reaches a tool:

    catalog lookup → manifest check → Policy Engine (G/Y/R) →
    Green: execute now · Yellow/Red: pending handle (executor deferred) ·
    violation: blocked — and every path writes a ``tool_invocations`` row.

The prompt-injection boundary: the gate's inputs are the code-defined
manifest/catalog and the user's standing allowances. Args and tool outputs
are data; nothing in them can change a tier or a verdict.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    PermissionTier,
    ToolDecision,
    ToolRunStatus,
)
from app.repositories import tool_invocation_repository as audit_repo
from app.services.agents.policy_engine import (
    PolicyDecision,
    evaluate,
)
from app.services.agents.registry import get_registry
from app.services.agents.tools.catalog import TOOL_CATALOG
from app.services.agents.tools.context import ToolContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolResult:
    """What an agent gets back from ``invoke`` — never an exception for a
    gate refusal (a blocked/pending call is a result, not an error).
    ``approval_id`` is the pending handle when the gate said "prompt"."""

    tool_key: str
    tier: PermissionTier
    decision: ToolDecision
    status: ToolRunStatus
    output: dict | None
    reason: str
    invocation_id: uuid.UUID
    approval_id: uuid.UUID | None = None


async def invoke(
    session: AsyncSession,
    *,
    tool_key: str,
    args: dict,
    agent_key: str,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    context: ToolContext,
    standing_allowances: frozenset[str] = frozenset(),
) -> ToolResult:
    """Gate + (for Green) execute one tool call, fully audited."""
    registry = get_registry()
    manifest = registry.get(agent_key)  # KeyError = orchestration bug

    spec = TOOL_CATALOG.get(tool_key)
    if spec is None:
        invocation = await audit_repo.record_invocation(
            session,
            user_id=user_id,
            run_id=run_id,
            agent_key=agent_key,
            tool_key=tool_key,
            args=args,
            tier=PermissionTier.RED,  # unknown capability: treat as maximal
            decision=ToolDecision.BLOCKED,
            status=ToolRunStatus.NOT_EXECUTED,
            decision_reason=f"unknown tool {tool_key!r}",
        )
        return ToolResult(
            tool_key=tool_key,
            tier=PermissionTier.RED,
            decision=ToolDecision.BLOCKED,
            status=ToolRunStatus.NOT_EXECUTED,
            output=None,
            reason=f"unknown tool {tool_key!r}",
            invocation_id=invocation.id,
        )

    verdict = evaluate(
        manifest=manifest,
        tool_key=tool_key,
        tool_tier=spec.tier,
        standing_allowances=standing_allowances,
    )

    approval_id: uuid.UUID | None = None
    if verdict.decision == PolicyDecision.BLOCK:
        decision, status = ToolDecision.BLOCKED, ToolRunStatus.NOT_EXECUTED
        output: dict | None = None
        error: str | None = None
    elif verdict.decision == PolicyDecision.PROMPT:
        # The human-in-the-loop seam (M10): create a previewed pending
        # approval and hand back its id. Deciding it later records the
        # decision only — no Yellow/Red executor exists in Phase 3.
        from app.services.agents import approval_service

        approval = await approval_service.create_pending(
            session,
            user_id=user_id,
            agent_key=agent_key,
            action_kind=tool_key,
            tier=spec.tier,
            preview={"tool_key": tool_key, "args": args},
            run_id=run_id,
        )
        approval_id = approval.id
        decision, status = ToolDecision.PENDING, ToolRunStatus.NOT_EXECUTED
        output, error = None, None
    elif spec.tier != PermissionTier.GREEN or spec.executor is None:
        # ALLOW above Green (standing allowance) — but Phase 3 wires no
        # non-Green executor, so nothing may run. Recorded as pending.
        decision, status = ToolDecision.PENDING, ToolRunStatus.NOT_EXECUTED
        output = None
        error = None
    else:
        decision = ToolDecision.ALLOWED
        try:
            output = await spec.executor(context, args)
            status, error = ToolRunStatus.SUCCEEDED, None
        except Exception as exc:
            logger.exception("green tool %s failed", tool_key)
            output, status, error = None, ToolRunStatus.FAILED, str(exc)

    invocation = await audit_repo.record_invocation(
        session,
        user_id=user_id,
        run_id=run_id,
        agent_key=agent_key,
        tool_key=tool_key,
        args=args,
        tier=spec.tier,
        decision=decision,
        status=status,
        decision_reason=verdict.reason,
        output_ref=(
            {"approval_id": str(approval_id)}
            if approval_id is not None
            else _output_preview(output)
        ),
        error=error,
    )
    return ToolResult(
        tool_key=tool_key,
        tier=spec.tier,
        decision=decision,
        status=status,
        output=output,
        reason=verdict.reason,
        invocation_id=invocation.id,
        approval_id=approval_id,
    )


def _output_preview(output: dict | None) -> dict | None:
    """A lean audit reference: top-level keys + sizes, not full payloads."""
    if output is None:
        return None
    return {
        key: (len(value) if isinstance(value, list | str) else value)
        for key, value in output.items()
    }
