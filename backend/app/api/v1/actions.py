"""Action-approval endpoints (``/api/v1/actions``) — thin HTTP (M10).

The confirm-before-acting surface. As of Phase 4, approving a tool-backed
action **does** fire its executor: the decision is committed first, then the
action runs from the stored preview and lands in the audit trail like any
other invocation (see ``services/agents/action_dispatch``). Rejecting still
records a decision and nothing else.

The tool and its arguments are read from the approval row, never from the
approve request, so this endpoint cannot be used to run an arbitrary call
under the authority of an approval granted for something else.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserId, DbSession
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.models.enums import ApprovalStatus
from app.schemas.action import (
    ActionApprovalDecisionResponse,
    ActionApprovalListResponse,
    ActionApprovalResponse,
    ActionExecutionResult,
)
from app.services.agents import action_dispatch, approval_service
from app.services.agents.tools import workspace as workspace_config
from app.services.agents.tools.context import ToolContext

router = APIRouter(prefix="/actions", tags=["actions"])


@router.get(
    "",
    response_model=ActionApprovalListResponse,
    summary="List action approvals (filter by status for the pending queue)",
)
async def list_actions(
    user_id: CurrentUserId,
    db: DbSession,
    status: ApprovalStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ActionApprovalListResponse:
    items, total = await approval_service.list_approvals(
        db, user_id=user_id, status=status, limit=limit, offset=offset
    )
    return ActionApprovalListResponse(
        items=[ActionApprovalResponse.model_validate(a) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{approval_id}",
    response_model=ActionApprovalResponse,
    summary="Get one action approval",
)
async def get_action(
    approval_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> ActionApprovalResponse:
    approval = await approval_service.get_approval(
        db, user_id=user_id, approval_id=approval_id
    )
    return ActionApprovalResponse.model_validate(approval)


@router.post(
    "/{approval_id}/approve",
    response_model=ActionApprovalDecisionResponse,
    summary="Approve a pending action and run it",
)
async def approve_action(
    approval_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> ActionApprovalDecisionResponse:
    """Approve, then execute, then report both outcomes separately.

    The decision commits first. If the action then fails, the approval stays
    approved and the failure is reported in ``execution`` — re-approving is
    refused, so a side-effecting command cannot be replayed by retrying.
    """
    approval = await approval_service.approve(
        db, user_id=user_id, approval_id=approval_id
    )
    result = await action_dispatch.dispatch_approved(
        db,
        approval,
        context=ToolContext(
            session=db,
            user_id=user_id,
            workspace=workspace_config.from_settings(),
        ),
    )
    return ActionApprovalDecisionResponse(
        approval=ActionApprovalResponse.model_validate(approval),
        execution=ActionExecutionResult(
            executed=result.executed,
            tool_key=result.tool_key,
            outcome=result.outcome.value if result.outcome else None,
            output=result.output,
            error=result.error,
            duration_ms=result.duration_ms,
            invocation_id=result.invocation_id,
        ),
    )


@router.post(
    "/{approval_id}/reject",
    response_model=ActionApprovalResponse,
    summary="Reject a pending action",
)
async def reject_action(
    approval_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> ActionApprovalResponse:
    approval = await approval_service.reject(
        db, user_id=user_id, approval_id=approval_id
    )
    return ActionApprovalResponse.model_validate(approval)
