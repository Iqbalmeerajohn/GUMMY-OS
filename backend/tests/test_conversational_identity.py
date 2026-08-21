"""Gummy's identity, and the honesty of what it claims it can do.

Prompted with two bland sentences and asked "what can you do?", a model has
nothing to answer from, so it invents a plausible assistant. Observed live:

    "I can help you with various tasks. From answering questions, to helping
     with reminders, to even assisting with coding projects like GUMMY..."

Every clause is guesswork — "coding projects like GUMMY" is the model reading
the word GUMMY out of its own prompt.

These tests assert behaviour and invariants, not wording. The important one is
that the capability text is *generated from the running system*: a hand-written
paragraph is a claim that starts rotting the day it is written, and the whole
point is that Gummy should not describe an agent that was removed or promise a
search backend that has no key.
"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services.agents.prompts import identity
from app.services.memory.context_assembly_service import ContextPackage
from app.services.memory.prompt_builder import build_prompt

_EMPTY = ContextPackage(memories=[], token_estimate=0)


def _system_for(query: str, *, knowledge: str | None = None) -> str:
    return build_prompt(context=_EMPTY, query=query, knowledge=knowledge).system


# ── Identity ─────────────────────────────────────────────────────────────────


def test_identity_names_the_product_not_a_generic_assistant() -> None:
    lowered = identity.IDENTITY.lower()
    assert "personal ai operating system" in lowered
    assert "not a generic chatbot" in lowered


def test_identity_bans_the_filler_openers() -> None:
    """The exact phrases the old build produced, named so they cannot return."""
    lowered = identity.IDENTITY.lower()
    assert "how can i assist you today" in lowered
    assert "i'm here to help" in lowered
    assert "variety of tasks" in lowered


def test_identity_ties_length_to_the_question() -> None:
    lowered = identity.IDENTITY.lower()
    assert "match length to the question" in lowered


def test_identity_forbids_narrating_the_machinery() -> None:
    """The user should experience Gummy, not its orchestrator."""
    assert "never describe your own machinery" in identity.IDENTITY.lower()


def test_the_identity_block_stays_short() -> None:
    """It rides on every turn, so it cannot crowd out the user's context."""
    assert len(identity.IDENTITY) < 1200


# ── Greetings ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "greeting",
    ["hello", "hi", "hey", "yo", "Hey Gummy", "Good morning", "hello!", "  hi  "],
)
def test_bare_greetings_are_recognised(greeting: str) -> None:
    assert identity.is_greeting(greeting)


@pytest.mark.parametrize(
    "message",
    [
        "hi, can you research LangGraph for me",
        "hello world program in python",
        "hey what is the capital of France",
        "say hello in french",
    ],
)
def test_a_greeting_with_a_request_attached_is_not_small_talk(message: str) -> None:
    """The length bound is what keeps "hi, do X" from being treated as hello."""
    assert not identity.is_greeting(message)


def test_a_greeting_gets_short_reply_guidance() -> None:
    system = _system_for("hello")
    assert identity._GREETING_GUIDANCE in system


def test_a_greeting_does_not_get_the_capability_list() -> None:
    """Answering "hi" with a feature dump is the failure being fixed."""
    system = _system_for("hello")
    assert "What you can genuinely do right now" not in system


# ── Capability questions ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "question",
    [
        "what can you do",
        "what can u do gummy",
        "What are your capabilities?",
        "how can you help me",
        "what is gummy",
        "who are you",
        "what do you do",
    ],
)
def test_capability_questions_are_recognised(question: str) -> None:
    assert identity.is_capability_question(question)


@pytest.mark.parametrize(
    "message",
    [
        "what is the capital of France",
        "teach me python",
        "what can I do to improve my resume",
        "find me a job",
    ],
)
def test_ordinary_questions_are_not_capability_questions(message: str) -> None:
    assert not identity.is_capability_question(message)


def test_a_capability_question_gets_the_real_capability_list() -> None:
    system = _system_for("what can u do gummy")
    assert "What you can genuinely do right now" in system
    assert "answer from THIS list" in system
    assert system.endswith(identity.capability_block())


def test_the_capability_block_specifies_a_shape_and_bans_vagueness() -> None:
    """Two failures, one instruction.

    Left alone the model copied the list out verbatim, which reads like
    documentation. Told instead to answer in flowing prose it paraphrased into
    "I can help with various tasks and queries" — the exact vagueness this
    block exists to prevent. The fix keeps the list and names the trap.
    """
    block = identity.capability_block()
    assert "not the sentences above copied out" in block
    assert "Stay specific" in block
    for vague in ("various tasks", "many things", "a wide range of topics"):
        assert vague in block, f"the banned phrase {vague!r} must be named"


def test_the_capability_list_is_generated_from_the_registry() -> None:
    """Not a hand-written paragraph: it names the agents that are registered."""
    from app.services.agents.registry import get_registry

    block = identity.capability_block()
    registered = get_registry().keys()

    if "career" in registered:
        assert "jobs" in block
    if "learning" in registered:
        assert "learning plans" in block
    if "automation" in registered:
        assert "reminders" in block


def test_the_capability_list_only_names_runnable_tools() -> None:
    """A modeled tool with no executor must never be advertised."""
    block = identity.capability_block()
    assert "exact calculations" in block
    assert "send an email" not in block.lower()
    assert "publish" not in block.lower()


def test_the_capability_list_states_its_limits() -> None:
    """A capability list that omits what is missing gets found out one question
    later, which is worse than saying so up front."""
    block = identity.capability_block().lower()
    assert "cannot send email or create calendar events" in block
    assert "only run while gummy is running" in block


def test_web_search_is_not_claimed_when_it_is_unconfigured() -> None:
    settings = get_settings()
    assert not settings.web_search_enabled, "test env should have no search key"

    block = identity.capability_block()

    assert "search the live web" not in block
    assert "live web search is not connected" in block


def test_web_search_is_claimed_once_it_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The generated block tracks configuration rather than a stale comment."""
    settings = get_settings()
    monkeypatch.setattr(settings, "agents_web_search_enabled", True)
    monkeypatch.setattr(settings, "tavily_api_key", "test-key")

    block = identity.capability_block()

    assert "search the live web" in block
    assert "live web search is not connected" not in block


# ── Everything else is left to the model ────────────────────────────────────


@pytest.mark.parametrize(
    "message",
    [
        "what is the capital of France",
        "Find AI/ML fresher jobs for me",
        "Teach me LangGraph",
        "Remind me tomorrow at 9am",
        "explain photosynthesis",
    ],
)
def test_ordinary_messages_get_no_extra_guidance(message: str) -> None:
    """This exists to fix two shapes, not to script conversations."""
    assert identity.guidance_for(message) == ""


def test_ordinary_prompts_are_unchanged_apart_from_the_persona() -> None:
    system = _system_for("what is the capital of France")
    assert identity._GREETING_GUIDANCE not in system
    assert "What you can genuinely do right now" not in system


@pytest.mark.parametrize("knowledge", [None, "Memories:\n- Lives in Bangalore"])
def test_per_message_guidance_lands_at_the_very_end(knowledge: str | None) -> None:
    """Placement, not just presence.

    In the middle of the prompt — ahead of the knowledge block — the guidance
    was measurably ignored: asked "hello", the local 3B model answered "How may
    I assist you?", paraphrasing its way around the ban. The most specific
    instruction has to sit closest to the message it is about.
    """
    system = _system_for("hello", knowledge=knowledge)
    assert system.endswith(identity._GREETING_GUIDANCE)


# ── Memory stays silent ──────────────────────────────────────────────────────


def test_the_knowledge_block_still_forbids_narrating_memory() -> None:
    system = _system_for("help me choose a learning path", knowledge="Memories:\n- x")
    lowered = system.lower()
    assert "use this context silently" in lowered
    assert "as you told me before" in lowered
    assert "do not announce that you remembered" in lowered


def test_a_greeting_with_knowledge_present_still_gets_short_guidance() -> None:
    """Both blocks compose; neither replaces the other."""
    system = _system_for("hello", knowledge="Memories:\n- Lives in Bangalore")
    assert identity._GREETING_GUIDANCE in system
    assert "Use this context silently" in system


# ── Formatting is conditional ────────────────────────────────────────────────


def test_formatting_rules_no_longer_demand_structure_everywhere() -> None:
    """They used to say "use short headers and bullet points" unconditionally,
    which pushed even "hello" toward a structured answer."""
    from app.services.agents.prompts.formatting import FORMATTING_RULES

    lowered = FORMATTING_RULES.lower()
    assert "structure is for content that needs it" in lowered
    assert "plain prose with no headers" in lowered
    assert "- use short headers and bullet points; keep lines tight." not in lowered


def test_formatting_rules_still_ban_markdown_tables() -> None:
    from app.services.agents.prompts.formatting import FORMATTING_RULES

    assert "NEVER output markdown tables" in FORMATTING_RULES
