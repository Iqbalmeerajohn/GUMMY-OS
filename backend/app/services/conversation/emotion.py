"""Mood detection — how the user sounds right now.

Deliberately a lexicon, not a model. This runs on the critical path of every
single turn, before the first token is generated, so its budget is microseconds;
a classifier call would cost more than the reply it is meant to shape. The
lexicon is small and blunt on purpose: it only has to separate "this person is
under pressure" from "this person is celebrating" well enough to change tone,
and a wrong guess costs a slightly-off greeting, not a wrong answer.

Nothing here is stored as a fact about the user. Mood is a property of a
*message*; only the aggregate baseline reaches the profile.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Mood(StrEnum):
    """The emotional register of a single message."""

    NEUTRAL = "neutral"
    POSITIVE = "positive"
    STRESSED = "stressed"
    SAD = "sad"
    FRUSTRATED = "frustrated"


# Cue words per mood. Matched on word boundaries so "stress" does not fire on
# "destressed" and "sad" does not fire on "sadly amusing"… which it would, but
# the cost of that is a gentler sentence, so it is accepted.
_CUES: dict[Mood, tuple[str, ...]] = {
    Mood.POSITIVE: (
        "thanks",
        "thank you",
        "awesome",
        "great",
        "excited",
        "love",
        "amazing",
        "perfect",
        "happy",
        "yay",
        "finally",
        "shipped",
        "done",
        "worked",
        "congrats",
    ),
    Mood.STRESSED: (
        "urgent",
        "asap",
        "deadline",
        "overwhelmed",
        "panic",
        "stressed",
        "stress",
        "pressure",
        "too much",
        "no time",
        "running out",
        "swamped",
        "anxious",
        "worried",
    ),
    Mood.SAD: (
        "sad",
        "down",
        "lonely",
        "depressed",
        "tired",
        "exhausted",
        "burnt out",
        "burned out",
        "hopeless",
        "lost",
        "give up",
    ),
    Mood.FRUSTRATED: (
        "not working",
        "broken",
        "again",
        "stuck",
        "annoying",
        "frustrated",
        "hate",
        "why doesn't",
        "why isn't",
        "still failing",
        "useless",
        "doesn't work",
    ),
}

_PATTERNS: dict[Mood, re.Pattern[str]] = {
    mood: re.compile(r"|".join(rf"\b{re.escape(c)}\b" for c in cues))
    for mood, cues in _CUES.items()
}

# Order matters when two registers tie: distress outranks delight, because
# missing that someone is struggling is the costlier mistake.
_PRIORITY: tuple[Mood, ...] = (
    Mood.STRESSED,
    Mood.FRUSTRATED,
    Mood.SAD,
    Mood.POSITIVE,
)


@dataclass(frozen=True)
class MoodReading:
    """A detected mood and how strongly the message signalled it."""

    mood: Mood
    intensity: float  # 0.0 (nothing detected) … 1.0 (several strong cues)


def detect(message: str) -> MoodReading:
    """Read the emotional register of one user message."""
    lowered = message.lower()
    hits = {mood: len(pattern.findall(lowered)) for mood, pattern in _PATTERNS.items()}
    # An all-caps shout or a pile of exclamation marks intensifies whatever is
    # already there, but never invents a mood on its own.
    emphasis = 0.2 if lowered.count("!") >= 2 else 0.0

    best = max(_PRIORITY, key=lambda m: (hits[m], -_PRIORITY.index(m)))
    if hits[best] == 0:
        return MoodReading(Mood.NEUTRAL, 0.0)

    intensity = min(1.0, 0.4 + 0.3 * (hits[best] - 1) + emphasis)
    return MoodReading(best, intensity)


# How Gummy should sound back. Warm without being saccharine, and — the part
# that matters — the work still gets done in the same reply.
_TONE: dict[Mood, str] = {
    Mood.STRESSED: (
        "The user sounds under time pressure. Lead with the answer or the "
        "single next action, keep it short, and skip preamble. Acknowledge the "
        "pressure in at most one clause — do not offer sympathy instead of help."
    ),
    Mood.FRUSTRATED: (
        "The user sounds frustrated, likely with something that keeps failing. "
        "Do not apologise repeatedly or restate the problem back to them. Give "
        "the most likely cause and a concrete fix first."
    ),
    Mood.SAD: (
        "The user sounds low or worn out. Be kind and unhurried, use plain "
        "warm language, and offer the smallest useful next step rather than a "
        "long plan. Still answer what they asked."
    ),
    Mood.POSITIVE: (
        "The user sounds pleased. Match the energy briefly and genuinely, then "
        "get on with the substance."
    ),
}


def tone_directive(reading: MoodReading) -> str | None:
    """The system-prompt line that adapts Gummy's delivery, if any.

    Returns ``None`` for a neutral or weakly-signalled message, which leaves the
    prompt unchanged — tone should shift when there is real evidence, not on
    every faint cue.
    """
    if reading.mood is Mood.NEUTRAL or reading.intensity < 0.4:
        return None
    return _TONE[reading.mood]
