"""Phase 4 tests: an approved action runs, is audited, and cannot be abused.

The interesting assertions here are the negative ones. Making an approved
action run is a few lines; making sure that is the *only* thing it can do is
the work:

* the call comes from the stored preview, not from the approve request;
* a withdrawn capability does not run on an old approval;
* a non-approved approval never dispatches;
* an approval whose run was deleted refuses rather than acting unaudited;
* the result is written to ``tool_invocations`` like any other call.
"""

from __future__ import annotations

import uuid
from pathlib import Path

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
from app.models.tool_invocation import ToolInvocation
from app.repositories import agent_run_repository as run_repo
from app.services.agents import action_dispatch, approval_service
from app.services.agents.tools.catalog import TOOL_CATALOG
from app.services.agents.tools.context import ToolContext
from app.services.agents.tools.executor import ToolOutcome
from app.services.agents.tools.workspace import Workspace


def _ctx(session: AsyncSession, user_id: uuid.UUID, root: Path) -> ToolContext:
    return ToolContext(
        session=session,
        user_id=user_id,
        workspace=Workspace(roots=(root.resolve(),)),
    )


async def _approved_write(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    path: Path,
    content: str = "approved content\n",
) -> ActionApproval:
    """A committed, approved `workspace_write` for ``path``."""
    run = await run_repo.create_run(session, user_id=user_id)
    await session.flush()
    approval = await approval_service.create_pending(
        session,
        user_id=user_id,
        agent_key="general",
        action_kind="workspace_write",
        tier=PermissionTier.YELLOW,
        preview={
            "tool_key": "workspace_write",
            "args": {"path": str(path), "content": content},
        },
        run_id=run.id,
    )
    await session.commit()
    return await approval_service.approve(
        session, user_id=user_id, approval_id=approval.id
    )


async def test_approved_write_actually_writes(
    db_session: AsyncSession, seed_user: uuid.UUID, tmp_path: Path
) -> None:
    target = tmp_path / "note.txt"
    approval = await _approved_write(db_session, seed_user, path=target)

    result = await action_dispatch.dispatch_approved(
        db_session, approval, context=_ctx(db_session, seed_user, tmp_path)
    )

    assert result.executed is True
    assert result.ok is True
    assert target.read_bytes() == b"approved content\n"


async def test_approved_action_writes_an_audit_row(
    db_session: AsyncSession, seed_user: uuid.UUID, tmp_path: Path
) -> None:
    """A consequential action must not be the one thing missing from the trail."""
    approval = await _approved_write(db_session, seed_user, path=tmp_path / "a.txt")
    result = await action_dispatch.dispatch_approved(
        db_session, approval, context=_ctx(db_session, seed_user, tmp_path)
    )

    row = (
        await db_session.execute(
            select(ToolInvocation).where(ToolInvocation.id == result.invocation_id)
        )
    ).scalar_one()
    assert row.tool_key == "workspace_write"
    assert row.tier is PermissionTier.YELLOW
    assert row.decision is ToolDecision.ALLOWED
    assert row.status is ToolRunStatus.SUCCEEDED


async def test_dispatch_uses_the_stored_preview_not_the_caller(
    db_session: AsyncSession, seed_user: uuid.UUID, tmp_path: Path
) -> None:
    """The whole security argument, as a test.

    ``dispatch_approved`` takes no args parameter at all — the only way to
    influence what runs is to change the approval a human already looked at.
    """
    intended = tmp_path / "intended.txt"
    approval = await _approved_write(db_session, seed_user, path=intended)

    await action_dispatch.dispatch_approved(
        db_session, approval, context=_ctx(db_session, seed_user, tmp_path)
    )

    assert intended.exists()
    assert not (tmp_path / "attacker.txt").exists()


async def test_pending_approval_does_not_dispatch(
    db_session: AsyncSession, seed_user: uuid.UUID, tmp_path: Path
) -> None:
    target = tmp_path / "never.txt"
    run = await run_repo.create_run(db_session, user_id=seed_user)
    await db_session.flush()
    approval = await approval_service.create_pending(
        db_session,
        user_id=seed_user,
        agent_key="general",
        action_kind="workspace_write",
        tier=PermissionTier.YELLOW,
        preview={
            "tool_key": "workspace_write",
            "args": {"path": str(target), "content": "x"},
        },
        run_id=run.id,
    )
    await db_session.commit()

    result = await action_dispatch.dispatch_approved(
        db_session, approval, context=_ctx(db_session, seed_user, tmp_path)
    )

    assert result.executed is False
    assert not target.exists()


async def test_rejected_approval_does_not_dispatch(
    db_session: AsyncSession, seed_user: uuid.UUID, tmp_path: Path
) -> None:
    target = tmp_path / "rejected.txt"
    run = await run_repo.create_run(db_session, user_id=seed_user)
    await db_session.flush()
    approval = await approval_service.create_pending(
        db_session,
        user_id=seed_user,
        agent_key="general",
        action_kind="workspace_write",
        tier=PermissionTier.YELLOW,
        preview={
            "tool_key": "workspace_write",
            "args": {"path": str(target), "content": "x"},
        },
        run_id=run.id,
    )
    await db_session.commit()
    rejected = await approval_service.reject(
        db_session, user_id=seed_user, approval_id=approval.id
    )

    result = await action_dispatch.dispatch_approved(
        db_session, rejected, context=_ctx(db_session, seed_user, tmp_path)
    )

    assert result.executed is False
    assert not target.exists()


async def test_withdrawn_capability_does_not_run(
    db_session: AsyncSession,
    seed_user: uuid.UUID,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An approval is not a licence to run a tool that no longer exists."""
    target = tmp_path / "gone.txt"
    approval = await _approved_write(db_session, seed_user, path=target)

    shrunk = {k: v for k, v in TOOL_CATALOG.items() if k != "workspace_write"}
    monkeypatch.setattr("app.services.agents.action_dispatch.TOOL_CATALOG", shrunk)

    result = await action_dispatch.dispatch_approved(
        db_session, approval, context=_ctx(db_session, seed_user, tmp_path)
    )

    assert result.executed is False
    assert result.outcome is ToolOutcome.UNAVAILABLE
    assert not target.exists()


async def test_approval_without_a_run_refuses_rather_than_acting_unaudited(
    db_session: AsyncSession, seed_user: uuid.UUID, tmp_path: Path
) -> None:
    """``tool_invocations.run_id`` is NOT NULL, so an orphaned approval
    cannot be recorded — and an unrecordable consequential action must not
    run at all."""
    target = tmp_path / "orphan.txt"
    approval = await _approved_write(db_session, seed_user, path=target)
    approval.run_id = None

    result = await action_dispatch.dispatch_approved(
        db_session, approval, context=_ctx(db_session, seed_user, tmp_path)
    )

    assert result.executed is False
    assert "audit trail" in (result.error or "")
    assert not target.exists()


async def test_non_tool_preview_is_not_a_dispatch(
    db_session: AsyncSession, seed_user: uuid.UUID, tmp_path: Path
) -> None:
    """Not every approval is a tool call; that is not an error."""
    run = await run_repo.create_run(db_session, user_id=seed_user)
    await db_session.flush()
    approval = await approval_service.create_pending(
        db_session,
        user_id=seed_user,
        agent_key="general",
        action_kind="something_else",
        tier=PermissionTier.YELLOW,
        preview={"summary": "a non-tool action"},
        run_id=run.id,
    )
    await db_session.commit()
    approved = await approval_service.approve(
        db_session, user_id=seed_user, approval_id=approval.id
    )

    result = await action_dispatch.dispatch_approved(
        db_session, approved, context=_ctx(db_session, seed_user, tmp_path)
    )

    assert result.executed is False
    assert "does not describe a tool call" in (result.error or "")


async def test_a_failing_action_is_reported_not_raised(
    db_session: AsyncSession, seed_user: uuid.UUID, tmp_path: Path
) -> None:
    """Approving a write that lands outside the workspace fails cleanly."""
    outside = tmp_path.parent / "escape.txt"
    approval = await _approved_write(db_session, seed_user, path=outside)

    result = await action_dispatch.dispatch_approved(
        db_session, approval, context=_ctx(db_session, seed_user, tmp_path)
    )

    assert result.executed is True
    assert result.ok is False
    assert result.outcome is ToolOutcome.FAILED
    assert not outside.exists()


async def test_double_approval_is_refused(
    db_session: AsyncSession, seed_user: uuid.UUID, tmp_path: Path
) -> None:
    """The status transition is the at-most-once guard for side effects."""
    approval = await _approved_write(db_session, seed_user, path=tmp_path / "once.txt")
    assert approval.status is ApprovalStatus.APPROVED

    with pytest.raises(approval_service.ApprovalAlreadyDecidedError):
        await approval_service.approve(
            db_session, user_id=seed_user, approval_id=approval.id
        )
