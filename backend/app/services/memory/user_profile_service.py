"""The learned user profile — who GUMMY thinks you are, kept current for free.

Individual memories answer "what do I know about this person"; this answers the
harder question of *who they are* in a form small enough to put in front of every
single prompt. It is maintained in two very different rhythms, and keeping them
separate is the whole design:

* :func:`observe` runs on the hot path of every turn. It is one primary-key
  fetch and a handful of arithmetic updates — counters, a rolling mean, a mood
  tally — so it costs about as much as the row lookup itself. Nothing here reads
  memories or calls a model.
* :func:`refresh_traits` runs off the hot path, after extraction has stored new
  facts. It re-derives the settled traits (name, location, work, project) from
  active memories, so the portrait follows corrections and supersessions for
  free instead of accumulating a second, stale copy of the truth.

:func:`render` is what the prompt sees. It stays deliberately short: a profile
block that grows without bound would push the actual retrieved context out of
the window, which is the opposite of remembering someone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MemoryStatus
from app.models.user_profile import UserProfile
from app.repositories import memory_repository as memory_repo
from app.services.conversation.emotion import Mood, MoodReading
from app.services.memory.instant_recall import INTENTS_BY_KEY, score_fact

# Traits worth carrying in every prompt. Each maps to a recall intent, so the
# selection logic that already decides "which stored fact is this person's name"
# is reused rather than reimplemented with a second set of keywords.
TRAIT_KEYS: tuple[str, ...] = ("name", "location", "work", "project")

# A trait has to be clearly the answer before it is stated as fact in the prompt;
# below this the model sees nothing and falls back on retrieved context.
_TRAIT_THRESHOLD = 0.45

# Candidates scanned per category when re-deriving traits. Same bound as instant
# recall: the newest few dozen facts in the right category contain the answer.
_TRAIT_CANDIDATES = 50

# Message-length bands for the style hint. Chosen from how people actually type:
# under ~60 characters is a fragment ("fix the build"), over ~320 is someone who
# writes paragraphs and expects them back.
_TERSE_CHARS = 60.0
_VERBOSE_CHARS = 320.0

# Before this many messages, "you tend to…" is noise dressed up as insight.
_STYLE_MIN_MESSAGES = 8
_MOOD_MIN_OBSERVATIONS = 6
_MOOD_MIN_SHARE = 0.3


async def load(session: AsyncSession, *, user_id: uuid.UUID) -> UserProfile:
    """Fetch this user's profile row, creating an empty one on first contact."""
    profile = await session.get(UserProfile, user_id)
    if profile is not None:
        return profile

    profile = UserProfile(
        user_id=user_id,
        traits={},
        mood_counts={},
        message_count=0,
        avg_message_chars=0.0,
        first_seen_at=datetime.now(UTC),
    )
    session.add(profile)
    await session.flush()
    return profile


async def observe(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    message: str,
    mood: MoodReading | None = None,
) -> UserProfile:
    """Record one user message against the profile. Hot path — keep it arithmetic.

    The rolling mean is updated incrementally so message length never requires
    reading history back, and the mood tally counts only messages that carried a
    real signal: neutral is the absence of evidence, not evidence of calm.
    """
    profile = await load(session, user_id=user_id)
    now = datetime.now(UTC)

    count = profile.message_count + 1
    # Welford-style incremental mean: no history read, no drift.
    profile.avg_message_chars += (len(message) - profile.avg_message_chars) / count
    profile.message_count = count
    profile.first_seen_at = profile.first_seen_at or now
    profile.last_seen_at = now
    profile.updated_at = now

    if mood is not None and mood.mood is not Mood.NEUTRAL:
        # JSON columns are not mutation-tracked, so rebind rather than mutate.
        counts = dict(profile.mood_counts or {})
        counts[mood.mood.value] = int(counts.get(mood.mood.value, 0)) + 1
        profile.mood_counts = counts

    return profile


async def refresh_traits(session: AsyncSession, *, user_id: uuid.UUID) -> UserProfile:
    """Re-derive settled traits from active memories. Off the hot path.

    Called after extraction has written new facts. Deriving rather than storing
    at write time is what keeps the portrait honest: when a memory is superseded
    or archived, the trait follows on the next refresh with no reconciliation
    step of its own.
    """
    profile = await load(session, user_id=user_id)
    traits: dict[str, str] = {}

    for key in TRAIT_KEYS:
        intent = INTENTS_BY_KEY.get(key)
        if intent is None:
            continue
        best_score = 0.0
        best_content: str | None = None
        for category in intent.categories:
            page, _total = await memory_repo.list_memories(
                session,
                user_id=user_id,
                category=category,
                status=MemoryStatus.ACTIVE,
                limit=_TRAIT_CANDIDATES,
                offset=0,
            )
            for memory in page:
                score = score_fact(memory.content, intent)
                if score > best_score:
                    best_score, best_content = score, memory.content
        if best_content is not None and best_score >= _TRAIT_THRESHOLD:
            traits[key] = best_content

    profile.traits = traits
    profile.updated_at = datetime.now(UTC)
    return profile


def _style_line(profile: UserProfile) -> str | None:
    if profile.message_count < _STYLE_MIN_MESSAGES:
        return None
    if profile.avg_message_chars <= _TERSE_CHARS:
        return "Writes in short fragments — answer just as briefly."
    if profile.avg_message_chars >= _VERBOSE_CHARS:
        return "Writes at length and expects thorough answers."
    return None


def _baseline_line(profile: UserProfile) -> str | None:
    """The user's emotional baseline, stated only when the evidence is real."""
    counts = {k: int(v) for k, v in (profile.mood_counts or {}).items()}
    total = sum(counts.values())
    if total < _MOOD_MIN_OBSERVATIONS:
        return None
    mood, hits = max(counts.items(), key=lambda pair: pair[1])
    if hits / total < _MOOD_MIN_SHARE:
        return None
    phrasing = {
        Mood.STRESSED.value: "Often under time pressure — lead with the answer.",
        Mood.FRUSTRATED.value: (
            "Often hits things that are broken — be concrete, skip apologies."
        ),
        Mood.SAD.value: "Often worn out — be warm and keep next steps small.",
        Mood.POSITIVE.value: "Generally upbeat — match that without gushing.",
    }
    return phrasing.get(mood)


def render(profile: UserProfile | None) -> str | None:
    """The prompt block, or None when there is genuinely nothing learned yet.

    Returning None matters: an empty ``<learned_profile>`` scaffold teaches the
    model that the section is usually blank, which weakens it once it fills in.
    """
    if profile is None:
        return None

    lines: list[str] = []
    labels = {
        "name": "Name",
        "location": "Location",
        "work": "Work",
        "project": "Working on",
    }
    for key in TRAIT_KEYS:
        value = (profile.traits or {}).get(key)
        if value:
            lines.append(f"{labels[key]}: {value}")

    for line in (_style_line(profile), _baseline_line(profile)):
        if line:
            lines.append(line)

    if not lines:
        return None
    body = "\n".join(lines)
    return f"<learned_profile>\n{body}\n</learned_profile>"
