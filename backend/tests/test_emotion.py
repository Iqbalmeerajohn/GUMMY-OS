"""Mood detection and the tone directive it produces."""

from __future__ import annotations

from app.services.conversation import emotion
from app.services.conversation.emotion import Mood


def test_plain_message_has_no_mood() -> None:
    assert emotion.detect("summarize this document").mood is Mood.NEUTRAL


def test_detects_time_pressure() -> None:
    reading = emotion.detect("this is urgent, the deadline is tomorrow")
    assert reading.mood is Mood.STRESSED
    assert reading.intensity >= 0.4


def test_detects_delight() -> None:
    assert emotion.detect("thanks, that worked perfectly!").mood is Mood.POSITIVE


def test_distress_outranks_delight_on_a_tie() -> None:
    """Missing that someone is struggling is the costlier mistake."""
    reading = emotion.detect("thanks but I'm still overwhelmed")
    assert reading.mood is Mood.STRESSED


def test_repeated_cues_and_emphasis_raise_intensity() -> None:
    mild = emotion.detect("this is broken")
    loud = emotion.detect("this is broken and stuck again!!")
    assert loud.intensity > mild.intensity


def test_neutral_message_leaves_the_prompt_unchanged() -> None:
    assert emotion.tone_directive(emotion.detect("list my files")) is None


def test_strong_signal_produces_a_directive() -> None:
    directive = emotion.tone_directive(emotion.detect("I'm swamped, this is urgent"))
    assert directive is not None
    assert "pressure" in directive.lower()
