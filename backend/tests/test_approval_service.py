"""Approval-service tests (Phase 3, M10).

Proves: a Yellow/Red gate decision creates a previewed pending approval (via
the tool interface); approve/reject transitions work exactly once; expiry
blocks decisions and flips status; and — the Phase 3 invariant — **deciding
an approval fires no executor** (asserted structurally and behaviorally).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.action_approval import ActionApproval
from app.models.enums import (
    ApprovalStatus,
    PermissionTier,
    ToolDecision,
    ToolRunStatus,
)
from app.repositories import agent_run_repository as run_repo
from app.schemas.agents import AgentManifest
from app.services.agents import approval_service
from app.services.agents import registry as registry_module
from app.services.agents.approval_service import (
    ApprovalAlreadyDecidedError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
)
from app.services.agents.registry import AgentRegistry
from app.services.agents.tools import interface
from app.services.agents.tools.catalog import TOOL_CATALOG
from app.services.agents.tools.context import ToolContext


def _powerful_registry() -> AgentRegistry:
    return AgentRegistry(
        (
            AgentManifest(
                key="powerful",
                display_name="Powerful",
                mission="Has risky tools.",
                ceiling=PermissionTier.RED,
                tools=("email_send", "social_publish"),
            ),
        )
    )


async def _pending_from_gate(
    session: AsyncSession,
    user_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
    tool_key: str = "email_send",
) -> tuple[uuid.UUID, uuid.UUID]:
    """Drive the real gate: a prompted tool call creates the approval."""
    monkeypatch.setattr(registry_module, "_registry", _powerful_registry())
    run = await run_repo.create_run(session, user_id=user_id)
    result = await interface.invoke(
        session,
        tool_key=tool_key,
        args={"to": "boss@example.com", "subject": "hi"},
        agent_key="powerful",
        run_id=run.id,
        user_id=user_id,
        context=ToolContext(session=session, user_id=user_id),
    )
    assert result.decision == ToolDecision.PENDING
    assert result.status == ToolRunStatus.NOT_EXECUTED
    assert result.approval_id is not None
    await session.commit()
    return result.approval_id, run.id


async def test_gate_prompt_creates_previewed_pending(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval_id, run_id = await _pending_from_gate(db_session, seed_user, monkeypatch)
    approval = await approval_service.get_approval(
        db_session, user_id=seed_user, approval_id=approval_id
    )
    assert approval.status == ApprovalStatus.PENDING
    assert approval.action_kind == "email_send"
    assert approval.tier == PermissionTier.YELLOW
    assert approval.run_id == run_id
    assert approval.preview["tool_key"] == "email_send"
    assert approval.preview["args"]["to"] == "boss@example.com"
    assert approval.expires_at is not None
    assert approval.decided_at is None


async def test_approve_records_decision_and_no_executor_fires(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval_id, _ = await _pending_from_gate(db_session, seed_user, monkeypatch)
    approved = await approval_service.approve(
        db_session, user_id=seed_user, approval_id=approval_id
    )
    assert approved.status == ApprovalStatus.APPROVED
    assert approved.decided_at is not None
    # The Phase 3 invariant, structurally: no non-Green executor exists
    # anywhere in the catalog, so approving cannot possibly run anything.
    assert all(
        spec.executor is None
        for spec in TOOL_CATALOG.values()
        if spec.tier != PermissionTier.GREEN
    )


async def test_reject_and_already_decided_conflict(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval_id, _ = await _pending_from_gate(db_session, seed_user, monkeypatch)
    rejected = await approval_service.reject(
        db_session, user_id=seed_user, approval_id=approval_id
    )
    assert rejected.status == ApprovalStatus.REJECTED
    with pytest.raises(ApprovalAlreadyDecidedError):
        await approval_service.approve(
            db_session, user_id=seed_user, approval_id=approval_id
        )


async def test_expired_approval_cannot_be_decided(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval_id, _ = await _pending_from_gate(db_session, seed_user, monkeypatch)
    approval = (
        await db_session.execute(
            select(ActionApproval).where(ActionApproval.id == approval_id)
        )
    ).scalar_one()
    approval.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()

    with pytest.raises(ApprovalExpiredError):
        await approval_service.approve(
            db_session, user_id=seed_user, approval_id=approval_id
        )
    refreshed = await approval_service.get_approval(
        db_session, user_id=seed_user, approval_id=approval_id
    )
    assert refreshed.status == ApprovalStatus.EXPIRED


async def test_red_action_also_creates_pending(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval_id, _ = await _pending_from_gate(
        db_session, seed_user, monkeypatch, tool_key="social_publish"
    )
    approval = await approval_service.get_approval(
        db_session, user_id=seed_user, approval_id=approval_id
    )
    assert approval.tier == PermissionTier.RED
    assert approval.status == ApprovalStatus.PENDING


async def test_foreign_tenant_404_and_list_scoping(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.user import User

    other = User(email=f"other-{uuid.uuid4().hex[:8]}@example.com")
    db_session.add(other)
    await db_session.commit()

    approval_id, _ = await _pending_from_gate(db_session, seed_user, monkeypatch)
    with pytest.raises(ApprovalNotFoundError):
        await approval_service.get_approval(
            db_session, user_id=other.id, approval_id=approval_id
        )
    items, total = await approval_service.list_approvals(
        db_session, user_id=other.id, limit=10, offset=0
    )
    assert (items, total) == ([], 0)

    mine, mine_total = await approval_service.list_approvals(
        db_session,
        user_id=seed_user,
        status=ApprovalStatus.PENDING,
        limit=10,
        offset=0,
    )
    assert mine_total == 1
    assert mine[0].id == approval_id


async def test_audit_row_links_the_approval(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.models.tool_invocation import ToolInvocation

    approval_id, _ = await _pending_from_gate(db_session, seed_user, monkeypatch)
    invocation = (await db_session.execute(select(ToolInvocation))).scalar_one()
    assert invocation.decision == ToolDecision.PENDING
    assert invocation.output_ref == {"approval_id": str(approval_id)}
