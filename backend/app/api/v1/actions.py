"""Action-approval endpoints (``/api/v1/actions``) — thin HTTP (M10).

The confirm-before-acting surface. Approving records a decision only;
no executor exists in Phase 3, so no endpoint here can fire a side effect.
A step-up-auth requirement for Red actions is a reserved seam for the
approval UI phase.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserId, DbSession
from app.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.models.enums import ApprovalStatus
from app.schemas.action import (
    ActionApprovalListResponse,
    ActionApprovalResponse,
)
from app.services.agents import approval_service

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
    response_model=ActionApprovalResponse,
    summary="Approve a pending action (records the decision; no executor)",
)
async def approve_action(
    approval_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> ActionApprovalResponse:
    approval = await approval_service.approve(
        db, user_id=user_id, approval_id=approval_id
    )
    return ActionApprovalResponse.model_validate(approval)


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
