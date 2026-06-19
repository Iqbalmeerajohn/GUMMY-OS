"""Profile context injection: JWT name extraction → identity block → prompt.

Pure, DB-free tests covering the full injection chain. Identity defaults to
``None`` everywhere, so the existing turn/agent parity tests prove the
non-injected path is byte-identical; these prove the injected path.
"""

from __future__ import annotations

import uuid

from app.core.security import _extract_name
from app.services.identity.user_context import (
    UserContext,
    build_identity_block,
)
from app.services.memory import context_assembly_service, prompt_builder


def _empty_context():
    return context_assembly_service.assemble_context(
        [], token_budget=2000, max_memories=20
    )


# ── JWT claim extraction (where identity was being lost) ──────────────────────


def test_extract_name_from_user_metadata_full_name() -> None:
    payload = {"sub": "x", "user_metadata": {"full_name": "Iqbal Meera John"}}
    assert _extract_name(payload) == "Iqbal Meera John"


def test_extract_name_prefers_full_name_then_name_then_first_name() -> None:
    assert _extract_name({"user_metadata": {"name": "Iqbal"}}) == "Iqbal"
    assert _extract_name({"user_metadata": {"first_name": "Iqbal"}}) == "Iqbal"


def test_extract_name_absent_returns_none() -> None:
    assert _extract_name({"sub": "x", "email": "a@b.com"}) is None
    assert _extract_name({"user_metadata": {"full_name": "   "}}) is None


# ── Identity block rendering (profile, not memory) ────────────────────────────


def test_identity_block_includes_name_and_marks_profile() -> None:
    ctx = UserContext(user_id=uuid.uuid4(), name="Iqbal", email="i@x.com")
    block = build_identity_block(ctx)
    assert block is not None
    assert "Iqbal" in block
    assert "<user_profile>" in block
    assert "prefer it over <memory>" in block.lower().replace("\n", " ")


def test_identity_block_none_when_no_name() -> None:
    ctx = UserContext(user_id=uuid.uuid4(), name=None, email="i@x.com")
    assert build_identity_block(ctx) is None
    assert build_identity_block(None) is None


def test_identity_block_never_exposes_user_id() -> None:
    uid = uuid.uuid4()
    block = build_identity_block(UserContext(user_id=uid, name="Iqbal", email=None))
    assert str(uid) not in (block or "")


def test_profile_completed_flag() -> None:
    assert UserContext(uuid.uuid4(), "Iqbal", "i@x.com").profile_completed is True
    assert UserContext(uuid.uuid4(), None, "i@x.com").profile_completed is False


# ── Prompt injection: identity precedes memory; None = unchanged ──────────────


def test_build_prompt_injects_identity_before_memory() -> None:
    ctx = UserContext(user_id=uuid.uuid4(), name="Iqbal", email="i@x.com")
    identity = build_identity_block(ctx)
    payload = prompt_builder.build_prompt(
        context=_empty_context(), query="What's my name?", identity=identity
    )
    assert "Iqbal" in payload.system
    # Identity block must come before the <memory> grounding.
    assert payload.system.index("Iqbal") < payload.system.index("<memory>")


def test_build_prompt_without_identity_is_unchanged() -> None:
    base = prompt_builder.build_prompt(context=_empty_context(), query="hi")
    with_none = prompt_builder.build_prompt(
        context=_empty_context(), query="hi", identity=None
    )
    assert base.system == with_none.system
    assert "<user_profile>" not in base.system
