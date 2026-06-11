"""Approval service — the human-in-the-loop decision flow (Phase 3, M10).

The Policy gate's "prompt" path creates a previewed pending approval (via
``create_pending``, flush-only — it rides the turn's unit of work). The API
paths (list/approve/reject) own their commit.

**Phase 3 invariant: deciding an approval performs no external side
effect.** Approving flips status and records ``decided_at`` — nothing more.
The Yellow/Red executors (and the re-dispatch of approved actions through
the Action Agent) are Phase 4 work, gated on the approval UI.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.action_approval import ActionApproval
from app.models.enums import ApprovalStatus, PermissionTier
from app.repositories import action_approval_repository as repo


class ApprovalNotFoundError(AppError):
    """Raised when an approval does not exist for this tenant."""

    def __init__(self, approval_id: uuid.UUID) -> None:
        super().__init__(
            f"Approval {approval_id} not found.",
            code="approval_not_found",
            status_code=404,
        )


class ApprovalAlreadyDecidedError(AppError):
    """Raised when deciding an approval that is no longer pending."""

    def __init__(self, status: ApprovalStatus) -> None:
        super().__init__(
            f"Approval is already {status.value}.",
            code="approval_already_decided",
            status_code=409,
        )


class ApprovalExpiredError(AppError):
    """Raised when deciding an approval past its expiry."""

    def __init__(self) -> None:
        super().__init__(
            "Approval has expired and can no longer be decided.",
            code="approval_expired",
            status_code=409,
        )


def _aware(moment: datetime) -> datetime:
    """SQLite returns naive datetimes for timezone-aware columns."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


async def create_pending(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    agent_key: str,
    action_kind: str,
    tier: PermissionTier,
    preview: dict,
    run_id: uuid.UUID | None = None,
) -> ActionApproval:
    """Create the pending handle for a prompted action. Flush-only."""
    return await repo.create_pending(
        session,
        user_id=user_id,
        agent_key=agent_key,
        action_kind=action_kind,
        tier=tier,
        preview=preview,
        run_id=run_id,
    )


async def get_approval(
    session: AsyncSession, *, user_id: uuid.UUID, approval_id: uuid.UUID
) -> ActionApproval:
    """Fetch one approval or raise 404."""
    approval = await repo.get_approval(
        session, approval_id=approval_id, user_id=user_id
    )
    if approval is None:
        raise ApprovalNotFoundError(approval_id)
    return approval


async def list_approvals(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    status: ApprovalStatus | None = None,
    limit: int,
    offset: int,
) -> tuple[list[ActionApproval], int]:
    """List approvals, newest first."""
    return await repo.list_approvals(
        session, user_id=user_id, status=status, limit=limit, offset=offset
    )


async def _decide(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    approval_id: uuid.UUID,
    status: ApprovalStatus,
) -> ActionApproval:
    approval = await get_approval(
        session, user_id=user_id, approval_id=approval_id
    )
    if approval.status is not ApprovalStatus.PENDING:
        raise ApprovalAlreadyDecidedError(approval.status)
    if _aware(approval.expires_at) <= datetime.now(UTC):
        # Stale previews must never be approvable: flip to expired, persist,
        # and reject the decision.
        await repo.set_decision(
            session, approval, status=ApprovalStatus.EXPIRED
        )
        await session.commit()
        raise ApprovalExpiredError()
    await repo.set_decision(session, approval, status=status)
    await session.commit()
    await session.refresh(approval)
    # Phase 3: the decision is recorded; NO executor fires here.
    return approval


async def approve(
    session: AsyncSession, *, user_id: uuid.UUID, approval_id: uuid.UUID
) -> ActionApproval:
    """Approve a pending action (records the decision only). Commits."""
    return await _decide(
        session,
        user_id=user_id,
        approval_id=approval_id,
        status=ApprovalStatus.APPROVED,
    )


async def reject(
    session: AsyncSession, *, user_id: uuid.UUID, approval_id: uuid.UUID
) -> ActionApproval:
    """Reject a pending action. Commits."""
    return await _decide(
        session,
        user_id=user_id,
        approval_id=approval_id,
        status=ApprovalStatus.REJECTED,
    )
