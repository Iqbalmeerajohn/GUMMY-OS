"""Prompt builder tests (pure, no DB)."""

from __future__ import annotations

from app.services.memory.context_assembly_service import (
    ContextMemory,
    ContextPackage,
)
from app.services.memory.prompt_builder import build_prompt


def _package(*memories: ContextMemory) -> ContextPackage:
    return ContextPackage(memories=list(memories), token_estimate=0)


def test_system_includes_persona_and_memory() -> None:
    package = _package(
        ContextMemory(content="Targeting Qualcomm", category="career", score=0.9)
    )
    payload = build_prompt(context=package, query="What am I preparing for?")

    assert "Gummy" in payload.system
    assert "Targeting Qualcomm" in payload.system
    assert "[career]" in payload.system
    assert "<memory>" in payload.system


def test_query_goes_into_user_message() -> None:
    payload = build_prompt(context=_package(), query="hello there")
    assert payload.messages == [{"role": "user", "content": "hello there"}]


def test_empty_context_states_no_memories() -> None:
    payload = build_prompt(context=_package(), query="anything")
    assert "No relevant memories" in payload.system


def test_history_is_prepended_before_query() -> None:
    history = [
        {"role": "user", "content": "earlier"},
        {"role": "assistant", "content": "reply"},
    ]
    payload = build_prompt(context=_package(), query="now", history=history)
    assert payload.messages == [*history, {"role": "user", "content": "now"}]


def test_rolling_summary_included_when_present() -> None:
    payload = build_prompt(
        context=_package(), query="hi", summary="We discussed RTOS scheduling."
    )
    assert "<conversation_summary>" in payload.system
    assert "We discussed RTOS scheduling." in payload.system


def test_no_summary_block_when_absent() -> None:
    payload = build_prompt(context=_package(), query="hi")
    assert "conversation_summary" not in payload.system
