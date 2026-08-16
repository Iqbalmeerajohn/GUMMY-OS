"""Instant recall — answer "what do you know about me" questions with no LLM.

Measured on this hardware, a generated reply costs ~2-3 seconds to first token,
whether it comes from the local GPU or a hosted API: network round-trip and
generation start dominate, and no amount of prompt tuning removes them. Sub-second
recall is therefore only reachable by *not generating* — reading the answer
straight out of memory and formatting it.

That is not a trick, because the questions this handles are exactly the ones with
a single correct answer already stored verbatim ("what's my name", "where do I
live", "what am I working on"). Running a language model over a fact it is only
allowed to repeat adds latency and a hallucination risk while adding nothing.

The design is conservative on purpose: **when in doubt, decline.** Returning
``None`` costs one wasted lookup (~2 ms) and falls through to the normal grounded
reply, whereas a confidently wrong instant answer is a visible product failure.
Three independent gates must all pass:

1. the question matches a known recall intent, and is short enough to be a direct
   question rather than a request that merely mentions one;
2. a stored memory matches that intent's category and keywords;
3. that memory wins by a clear margin over the runner-up, so genuinely ambiguous
   cases go to the model instead of picking arbitrarily.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryCategory, MemoryStatus
from app.repositories import memory_repository as memory_repo

# Per category. Recall questions are answered by a specific stored fact, and the
# newest few dozen in the right category always contain it if it exists — this
# is a bound on worst-case latency, not a retrieval-quality knob.
_CANDIDATES_PER_CATEGORY = 50

# A direct question is short. "What is my name?" qualifies; "write a cover letter
# using my name and the job description below" mentions the same words but wants
# a generated answer, and this length ceiling is what separates the two cheaply.
_MAX_DIRECT_QUESTION_WORDS = 12

# How far ahead the best match must be before we answer without the model.
# Below this, two memories are competing (e.g. two stored locations) and picking
# one silently would be guessing.
_CONFIDENCE_MARGIN = 0.15


@dataclass(frozen=True)
class RecallIntent:
    """One recognizable question about the user's own stored facts."""

    key: str
    # Matched against the whole normalized question.
    patterns: tuple[str, ...]
    # Memory categories worth searching for this intent.
    categories: tuple[MemoryCategory, ...]
    # Words that make a stored memory a likely answer to this intent.
    signals: tuple[str, ...]
    # How the answer is phrased. ``{fact}`` is the stored memory's content.
    template: str


_INTENTS: tuple[RecallIntent, ...] = (
    RecallIntent(
        key="name",
        patterns=(r"\bwhat('?s| is)? my name\b", r"\bwho am i\b", r"\bmy name\b"),
        categories=(MemoryCategory.PROFILE,),
        signals=("name", "called", "i am", "i'm"),
        template="{fact}",
    ),
    RecallIntent(
        key="location",
        patterns=(
            r"\bwhere do i live\b",
            r"\bwhere am i (from|based)\b",
            r"\bmy (location|city|hometown)\b",
        ),
        categories=(MemoryCategory.PROFILE,),
        signals=("live", "lives", "from", "based", "city", "located"),
        template="{fact}",
    ),
    RecallIntent(
        key="work",
        patterns=(
            r"\bwhat (do i do|is my job)\b",
            r"\bwhere do i work\b",
            r"\bmy (job|role|career|profession)\b",
        ),
        categories=(MemoryCategory.CAREER, MemoryCategory.PROJECT),
        signals=("work", "works", "job", "role", "engineer", "developer", "student"),
        template="{fact}",
    ),
    RecallIntent(
        key="project",
        patterns=(
            r"\bwhat am i (building|working on)\b",
            r"\bmy (project|projects)\b",
        ),
        categories=(MemoryCategory.PROJECT,),
        signals=("building", "project", "working on", "developing"),
        template="{fact}",
    ),
    RecallIntent(
        key="preference",
        patterns=(
            r"\bwhat('?s| is)? my favou?rite\b",
            r"\bwhat do i (like|love|prefer)\b",
        ),
        categories=(MemoryCategory.PREFERENCE,),
        signals=("favorite", "favourite", "likes", "loves", "prefers", "enjoys"),
        template="{fact}",
    ),
)

# Keyed lookup for callers that already know which fact they want (the
# incremental user profile asks for "name" or "location" directly rather
# than matching a question).
INTENTS_BY_KEY: dict[str, RecallIntent] = {i.key: i for i in _INTENTS}

_NORMALIZE = re.compile(r"[^a-z0-9\s'?]+")


def _normalize(text: str) -> str:
    return _NORMALIZE.sub(" ", text.lower()).strip()


def detect_intent(message: str) -> RecallIntent | None:
    """Identify a direct recall question, or None.

    Length is checked first because it is the cheapest discriminator and it is
    what stops a long task ("draft a bio using my name and city") from being
    mistaken for a question about the user.
    """
    normalized = _normalize(message)
    if len(normalized.split()) > _MAX_DIRECT_QUESTION_WORDS:
        return None
    for intent in _INTENTS:
        if any(re.search(pattern, normalized) for pattern in intent.patterns):
            return intent
    return None


def score_fact(content: str, intent: RecallIntent) -> float:
    """How well a stored memory answers this intent, in [0, 1].

    Deliberately lexical rather than semantic: the candidate set is already
    narrowed by category, and an embedding call here would reintroduce exactly
    the latency this module exists to avoid.
    """
    lowered = content.lower()
    hits = sum(1 for signal in intent.signals if signal in lowered)
    if hits == 0:
        return 0.0
    coverage = hits / len(intent.signals)
    # Shorter memories are better answers: "Lives in Vizag" answers a question
    # about location, while a paragraph that happens to mention living somewhere
    # buries it.
    brevity = 1.0 if len(content) <= 80 else 80 / len(content)
    return min(1.0, 0.7 * coverage + 0.3 * brevity)


@dataclass(frozen=True)
class InstantAnswer:
    """A recall answer produced without invoking a language model."""

    text: str
    memory_id: uuid.UUID
    intent_key: str
    confidence: float


async def try_answer(
    session: AsyncSession, *, user_id: uuid.UUID, message: str
) -> InstantAnswer | None:
    """Answer a direct recall question from memory, or return None to fall through.

    Returning None is the safe, common case and must stay cheap — it costs one
    regex sweep plus, at most, one indexed query.
    """
    intent = detect_intent(message)
    if intent is None:
        return None

    candidates = []
    for category in intent.categories:
        page, _total = await memory_repo.list_memories(
            session,
            user_id=user_id,
            category=category,
            status=MemoryStatus.ACTIVE,
            limit=_CANDIDATES_PER_CATEGORY,
            offset=0,
        )
        candidates.extend(page)
    if not candidates:
        return None

    scored = sorted(
        ((score_fact(m.content, intent), m) for m in candidates),
        key=lambda pair: pair[0],
        reverse=True,
    )
    best_score, best = scored[0]
    if best_score <= 0.0:
        return None

    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    if best_score - runner_up < _CONFIDENCE_MARGIN:
        # Two stored facts answer this equally well. Let the model reconcile
        # them rather than silently choosing one.
        return None

    return InstantAnswer(
        text=intent.template.format(fact=best.content.rstrip(".")) + ".",
        memory_id=best.id,
        intent_key=intent.key,
        confidence=best_score,
    )
