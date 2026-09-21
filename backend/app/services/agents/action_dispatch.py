"""Phase 4: running an action after a human approved it.

Phase 3 stopped deliberately short. The Policy gate produced a previewed
pending approval, the user could approve or reject it, and approving recorded
the decision and did nothing else — the comment in ``approval_service`` says so
plainly: *"no executor fires here."* That was the right place to stop while the
approval UI did not exist, but it left every Yellow and Red tool permanently
inert. A capability that can be declared, routed, gated and approved but never
run is a promise the product does not keep.

This module closes that loop, and the shape of it is the security argument:

**The approved action is re-read from the database, never from the request.**
The caller supplies an approval id and nothing else. Tool key and arguments
come from the stored ``preview`` — the same bytes a human looked at when they
approved. If the arguments came from the request, "approve" would degenerate
into "run whatever I send with the authority of an approval".

**Approval is not a tier override.** The spec is looked up in the catalog again
and re-validated. An approval for a tool that has since been removed, or had
its executor withdrawn, does not run.

**Execution happens exactly once.** The status transition pending → approved is
the guard: ``_decide`` refuses a non-pending approval, so a double-click cannot
produce two writes or two shell commands. The transition is committed *before*
the executor runs, which is the deliberate choice — it means a crash mid-action
leaves the approval marked approved with no result recorded, rather than
leaving it pending and inviting a second run of a side-effecting command. For
irreversible actions, at-most-once beats at-least-once.

**The result is audited like any other invocation.** An approved action lands
in ``tool_invocations`` exactly as a Green call does, so the audit trail does
not have a hole where the consequential actions are.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_approval import ActionApproval
from app.models.enums import (
    ApprovalStatus,
    PermissionTier,
    ToolDecision,
    ToolRunStatus,
)
from app.repositories import tool_invocation_repository as audit_repo
from app.services.agents.tools import executor as tool_executor
from app.services.agents.tools.catalog import TOOL_CATALOG
from app.services.agents.tools.context import ToolContext
from app.services.agents.tools.executor import ToolOutcome

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DispatchResult:
    """What happened when an approved action was run."""

    approval_id: uuid.UUID
    tool_key: str
    executed: bool
    outcome: ToolOutcome | None = None
    output: dict | None = None
    error: str | None = None
    duration_ms: float = 0.0
    invocation_id: uuid.UUID | None = None

    @property
    def ok(self) -> bool:
        return self.executed and self.outcome is ToolOutcome.SUCCESS


def _preview_call(approval: ActionApproval) -> tuple[str, dict] | None:
    """Extract ``(tool_key, args)`` from a stored preview, if it holds one.

    Approvals are not all tool calls — the model allows for other action kinds
    — so a preview without a tool shape is a legitimate "nothing to dispatch",
    not an error.
    """
    preview = approval.preview or {}
    if not isinstance(preview, dict):
        return None
    tool_key = preview.get("tool_key")
    args = preview.get("args")
    if not isinstance(tool_key, str) or not tool_key:
        return None
    if not isinstance(args, dict):
        args = {}
    return tool_key, args


async def dispatch_approved(
    session: AsyncSession,
    approval: ActionApproval,
    *,
    context: ToolContext,
) -> DispatchResult:
    """Run the action an approval authorised, and audit the result.

    The approval must already be committed as ``approved``; this function does
    not decide anything. It never raises for the action's own failure — a
    failed command is a result the user should see, not a 500.
    """
    if approval.status is not ApprovalStatus.APPROVED:
        return DispatchResult(
            approval_id=approval.id,
            tool_key=str(approval.action_kind),
            executed=False,
            error="approval is not in the approved state",
        )

    call = _preview_call(approval)
    if call is None:
        return DispatchResult(
            approval_id=approval.id,
            tool_key=str(approval.action_kind),
            executed=False,
            error="this approval does not describe a tool call",
        )
    tool_key, args = call

    # ``action_approvals.run_id`` is SET NULL on run cleanup, but
    # ``tool_invocations.run_id`` is NOT NULL — so an approval that outlived
    # its run cannot be audited. Rather than run the action and lose the
    # record, refuse: a consequential action that cannot be written to the
    # trail is exactly what this design declines to perform.
    if approval.run_id is None:
        reason = (
            "the originating run no longer exists, so this action cannot be "
            "recorded in the audit trail and will not be run."
        )
        logger.warning("refusing approval %s: %s", approval.id, reason)
        return DispatchResult(
            approval_id=approval.id,
            tool_key=tool_key,
            executed=False,
            outcome=ToolOutcome.UNAVAILABLE,
            error=reason,
        )

    spec = TOOL_CATALOG.get(tool_key)
    if spec is None or not spec.is_executable:
        # The capability was withdrawn between preview and approval. Record
        # the attempt so the trail shows why nothing happened.
        reason = (
            f"unknown tool {tool_key!r}"
            if spec is None
            else f"{spec.name} is declared but not available in this build."
        )
        invocation = await audit_repo.record_invocation(
            session,
            user_id=approval.user_id,
            run_id=approval.run_id,
            agent_key=approval.agent_key,
            tool_key=tool_key,
            args=args,
            tier=spec.tier if spec else PermissionTier.RED,
            decision=ToolDecision.PENDING,
            status=ToolRunStatus.NOT_EXECUTED,
            decision_reason=reason,
        )
        await session.commit()
        return DispatchResult(
            approval_id=approval.id,
            tool_key=tool_key,
            executed=False,
            outcome=ToolOutcome.UNAVAILABLE,
            error=reason,
            invocation_id=invocation.id,
        )

    logger.info(
        "dispatching approved %s action %s (approval=%s)",
        spec.tier.value,
        tool_key,
        approval.id,
    )
    # The executor owns validation, the timeout, and turning every ending into
    # a structured outcome — the same path a Green call takes, so an approved
    # action cannot skip any of it.
    execution = await tool_executor.run(spec, context, args)

    invocation = await audit_repo.record_invocation(
        session,
        user_id=approval.user_id,
        run_id=approval.run_id,
        agent_key=approval.agent_key,
        tool_key=tool_key,
        args=args,
        tier=spec.tier,
        decision=ToolDecision.ALLOWED,
        status=(ToolRunStatus.SUCCEEDED if execution.ok else ToolRunStatus.FAILED),
        decision_reason=f"approved by user (approval {approval.id})",
        error=execution.error,
    )
    await session.commit()

    return DispatchResult(
        approval_id=approval.id,
        tool_key=tool_key,
        executed=True,
        outcome=execution.outcome,
        output=execution.output,
        error=execution.error,
        duration_ms=execution.duration_ms,
        invocation_id=invocation.id,
    )
