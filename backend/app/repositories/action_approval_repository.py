"""Data-access layer for action_approvals (persistence only, no commit)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ACTION_APPROVAL_TTL_SECONDS
from app.models.action_approval import ActionApproval
from app.models.enums import ApprovalStatus, PermissionTier


async def create_pending(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    agent_key: str,
    action_kind: str,
    tier: PermissionTier,
    preview: dict,
    run_id: uuid.UUID | None = None,
    ttl_seconds: int = ACTION_APPROVAL_TTL_SECONDS,
) -> ActionApproval:
    """Insert a pending approval with its expiry and flush."""
    approval = ActionApproval(
        user_id=user_id,
        run_id=run_id,
        agent_key=agent_key,
        action_kind=action_kind,
        tier=tier,
        preview=preview,
        status=ApprovalStatus.PENDING,
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )
    session.add(approval)
    await session.flush()
    return approval


async def get_approval(
    session: AsyncSession,
    *,
    approval_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ActionApproval | None:
    """Fetch one tenant-scoped approval by id, if it exists."""
    stmt = select(ActionApproval).where(
        ActionApproval.id == approval_id,
        ActionApproval.user_id == user_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_approvals(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    status: ApprovalStatus | None = None,
    limit: int,
    offset: int,
) -> tuple[list[ActionApproval], int]:
    """Return a page of approvals (newest first) and the total."""
    filters = [ActionApproval.user_id == user_id]
    if status is not None:
        filters.append(ActionApproval.status == status)
    total = await session.scalar(
        select(func.count()).select_from(ActionApproval).where(*filters)
    )
    stmt = (
        select(ActionApproval)
        .where(*filters)
        .order_by(ActionApproval.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows), int(total or 0)


async def set_decision(
    session: AsyncSession,
    approval: ActionApproval,
    *,
    status: ApprovalStatus,
) -> ActionApproval:
    """Record a decision (status + ``decided_at``). Flush-only."""
    approval.status = status
    approval.decided_at = datetime.now(UTC)
    await session.flush()
    return approval
