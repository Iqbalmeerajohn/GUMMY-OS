"""Automations API — list, inspect, pause/resume, and delete scheduled tasks.

Creation deliberately has no endpoint here. Automations are created through
conversation (the Automation Agent's ``automation_create`` tool), which keeps
one path into the table and means every automation carries the agent trace and
audit row that path produces.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserId, DbSession
from app.services.automation import automation_service

router = APIRouter(prefix="/automations", tags=["automations"])


class AutomationRunResponse(BaseModel):
    """One firing of an automation."""

    id: uuid.UUID
    scheduled_for: str
    status: str
    finished_at: str | None = None
    output: str | None = None
    error: str | None = None


class AutomationResponse(BaseModel):
    """An automation as the client sees it."""

    id: uuid.UUID
    name: str
    description: str | None = None
    kind: str
    schedule: str
    status: str
    enabled: bool
    timezone: str
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_error: str | None = None
    created_at: str


class AutomationListResponse(BaseModel):
    items: list[AutomationResponse]
    total: int


class AutomationToggleRequest(BaseModel):
    enabled: bool = Field(description="True to resume, false to pause.")


def _to_response(automation: object) -> AutomationResponse:
    a = automation
    return AutomationResponse(
        id=a.id,  # type: ignore[attr-defined]
        name=a.name,  # type: ignore[attr-defined]
        description=a.description,  # type: ignore[attr-defined]
        kind=a.kind.value,  # type: ignore[attr-defined]
        schedule=a.schedule.value,  # type: ignore[attr-defined]
        status=a.status.value,  # type: ignore[attr-defined]
        enabled=a.enabled,  # type: ignore[attr-defined]
        timezone=a.timezone,  # type: ignore[attr-defined]
        next_run_at=(
            a.next_run_at.isoformat() if a.next_run_at else None  # type: ignore[attr-defined]
        ),
        last_run_at=(
            a.last_run_at.isoformat() if a.last_run_at else None  # type: ignore[attr-defined]
        ),
        last_error=a.last_error,  # type: ignore[attr-defined]
        created_at=a.created_at.isoformat(),  # type: ignore[attr-defined]
    )


@router.get(
    "",
    response_model=AutomationListResponse,
    summary="List the user's scheduled automations",
)
async def list_automations(
    user_id: CurrentUserId,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AutomationListResponse:
    items, total = await automation_service.list_for_user(
        db, user_id=user_id, limit=limit, offset=offset
    )
    return AutomationListResponse(items=[_to_response(a) for a in items], total=total)


@router.get(
    "/{automation_id}",
    response_model=AutomationResponse,
    summary="Get one automation",
)
async def get_automation(
    automation_id: uuid.UUID, user_id: CurrentUserId, db: DbSession
) -> AutomationResponse:
    automation = await automation_service.get(
        db, user_id=user_id, automation_id=automation_id
    )
    return _to_response(automation)


@router.get(
    "/{automation_id}/runs",
    response_model=list[AutomationRunResponse],
    summary="An automation's recent runs",
)
async def list_runs(
    automation_id: uuid.UUID, user_id: CurrentUserId, db: DbSession
) -> list[AutomationRunResponse]:
    from app.repositories import automation_repository as repo

    # Ownership first: a 404 for someone else's id, never a run list.
    await automation_service.get(db, user_id=user_id, automation_id=automation_id)
    runs = await repo.list_runs(db, automation_id=automation_id, user_id=user_id)
    return [
        AutomationRunResponse(
            id=r.id,
            scheduled_for=r.scheduled_for.isoformat(),
            status=r.status.value,
            finished_at=r.finished_at.isoformat() if r.finished_at else None,
            output=r.output,
            error=r.error,
        )
        for r in runs
    ]


@router.post(
    "/{automation_id}/toggle",
    response_model=AutomationResponse,
    summary="Pause or resume an automation",
)
async def toggle_automation(
    automation_id: uuid.UUID,
    payload: AutomationToggleRequest,
    user_id: CurrentUserId,
    db: DbSession,
) -> AutomationResponse:
    automation = await automation_service.set_enabled(
        db, user_id=user_id, automation_id=automation_id, enabled=payload.enabled
    )
    return _to_response(automation)


@router.delete(
    "/{automation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an automation",
)
async def delete_automation(
    automation_id: uuid.UUID, user_id: CurrentUserId, db: DbSession
) -> None:
    await automation_service.delete(db, user_id=user_id, automation_id=automation_id)
