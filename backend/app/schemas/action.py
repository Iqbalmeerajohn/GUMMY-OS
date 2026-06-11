"""Pydantic schemas for action approvals (the M10 wire contract)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ApprovalStatus, PermissionTier


class ActionApprovalResponse(BaseModel):
    """An approval as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    run_id: uuid.UUID | None
    agent_key: str
    action_kind: str
    tier: PermissionTier
    preview: dict
    status: ApprovalStatus
    decided_at: datetime | None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class ActionApprovalListResponse(BaseModel):
    """A paginated list of approvals (newest first)."""

    items: list[ActionApprovalResponse]
    total: int
    limit: int
    offset: int
