"""Milestone endpoints (``/api/v1/milestones``) — thin HTTP over the service.

Milestone *creation* is goal-scoped and lives in :mod:`app.api.v1.goals`
(``POST /goals/{id}/milestones``); these routes handle mutation of an existing
milestone by its own id.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUserId, DbSession
from app.schemas.goal import MilestoneResponse, MilestoneUpdate
from app.services.goals import milestone_service

router = APIRouter(prefix="/milestones", tags=["goals"])


@router.patch(
    "/{milestone_id}",
    response_model=MilestoneResponse,
    summary="Update a milestone (title / completed / order)",
)
async def update_milestone(
    milestone_id: uuid.UUID,
    payload: MilestoneUpdate,
    user_id: CurrentUserId,
    db: DbSession,
) -> MilestoneResponse:
    milestone = await milestone_service.update_milestone(
        db, user_id=user_id, milestone_id=milestone_id, payload=payload
    )
    return MilestoneResponse.model_validate(milestone)


@router.delete(
    "/{milestone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a milestone",
)
async def delete_milestone(
    milestone_id: uuid.UUID,
    user_id: CurrentUserId,
    db: DbSession,
) -> None:
    await milestone_service.delete_milestone(
        db, user_id=user_id, milestone_id=milestone_id
    )
