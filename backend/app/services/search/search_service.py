"""Search service — the agent-facing front door to web search (M8.5, B3).

One place that turns "this agent wants live context for this query" into a
normalized, deduped, ranked, capped list of :class:`SearchResult`. Callers (the
specialist handler and the streaming turn) depend only on this module + the
``SearchProvider`` seam — never on a concrete backend.

Responsibilities (the brief, B3):
  * **gate** — ``is_search_eligible`` keeps live search off most turns: only the
    Research/Career/Learning specialists, and only when the query looks
    search-worthy (recency/lookup cues). Conserves spend (search costs per call).
  * **query** the active provider (best-effort; the provider never raises).
  * **normalize / dedupe / rank / limit** the hits into supplemental context.
  * **observe** — Langfuse spans (``search.query`` / ``search.rank`` /
    ``search.summarize``) + local analytics events (``SearchPerformed`` /
    ``SearchResultsReturned``).

Best-effort by contract: every entrypoint returns ``[]`` rather than raising, so
a search outage never costs the user a reply (B10).
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from app.core.config import get_settings
from app.core.constants import SEARCH_DEFAULT_LIMIT
from app.observability import analytics
from app.observability import langfuse as langfuse_obs
from app.services.search.provider import (
    SearchProviderError,
    SearchResult,
    get_provider,
    is_live,
)

logger = logging.getLogger(__name__)


class SearchStatus(StrEnum):
    """Why a search did or did not produce evidence.

    Four states, because collapsing them loses the distinction that matters.
    ``NO_RESULTS`` is a fact about the world; ``UNAVAILABLE`` and ``FAILED``
    are facts about us. A model handed an empty list cannot tell which it is
    looking at, and reliably narrates the flattering one.
    """

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    NO_RESULTS = "no_results"


@dataclass(frozen=True)
class SearchOutcome:
    """The result of asking for evidence, including the ways it can go wrong."""

    status: SearchStatus
    results: list[SearchResult] = field(default_factory=list)
    query: str = ""

    @property
    def has_evidence(self) -> bool:
        """True only when live results actually came back.

        The single question every caller should ask before treating anything
        as a current fact.
        """
        return self.status is SearchStatus.AVAILABLE and bool(self.results)


# Specialists allowed to spend on live search (B4/B5/B6). Memory/Planner/General
# answer from the user's own knowledge and never hit the network.
SEARCH_ELIGIBLE_AGENTS: frozenset[str] = frozenset({"research", "career", "learning"})

# Query cues that mark a turn as search-worthy. Substring match on the lowered
# query (kept broad but cheap); pairs the recency/lookup intent the brief lists
# ("Latest AI news", "Find AI Engineer jobs", "Best transformer tutorials").
_SEARCH_CUES: tuple[str, ...] = (
    "latest",
    "recent",
    "current",
    "today",
    "this year",
    "news",
    "trend",
    "update",
    "release",
    "new ",
    "find ",
    "search",
    "look up",
    "lookup",
    "best ",
    "top ",
    "compare",
    "vs ",
    "versus",
    "job",
    "internship",
    "course",
    "tutorial",
    "hiring",
    "salary",
    "price",
    "review",
)
# Any 4-digit year 2024+ is a recency cue ("openings in 2025").
_YEAR_RE = re.compile(r"\b20(2[4-9]|[3-9]\d)\b")

# ── Freshness ────────────────────────────────────────────────────────────────
#
# A narrower question than "might search help?": would the answer be *wrong*
# without current evidence? "Compare RAG and fine-tuning" benefits from search
# but is perfectly answerable from a model. "What are the latest AI agent
# releases" is not — any answer given without evidence is a guess wearing the
# costume of a finding.
#
# So this list holds recency and volatility markers only. Deliberately absent:
# "compare", "best", "top", "find", "vs", "tutorial", "course", "review" — all
# present in _SEARCH_CUES above, none of them about time. Treating those as
# freshness-critical would refuse to answer ordinary teaching questions.
_FRESHNESS_MARKERS: tuple[str, ...] = (
    "latest",
    "most recent",
    "recent",
    "currently",
    "current",
    "right now",
    "as of today",
    "today",
    "yesterday",
    "this week",
    "this month",
    "this year",
    "these days",
    "up to date",
    "up-to-date",
    "newest",
    # The idiom, not the bare word: "new" alone fires on "new to Python" and
    # "a new resume", which are not questions about the present.
    "what's new",
    "whats new",
    "what is new",
    "just released",
    "just announced",
    "news",
    "headlines",
    "trending",
    "nowadays",
)

# Volatile subjects: even without a time word, the answer decays fast enough
# that stating it from model memory is a claim about the present.
_VOLATILE_MARKERS: tuple[str, ...] = (
    "job opening",
    "job openings",
    "hiring",
    "who is hiring",
    "price",
    "pricing",
    "stock",
    "share price",
    "valuation",
    "funding round",
    "raised",
    "acquisition",
    "released",
    "release date",
    "version",
    "changelog",
    "deadline",
    "last date",
)


def requires_fresh_evidence(query: str) -> bool:
    """True when answering without live evidence would be a guess about now.

    Conservative on purpose, and separate from :func:`is_search_eligible`.
    Eligibility decides whether spending a search call is worthwhile;
    this decides whether an answer *without* one is honest.
    """
    lowered = query.lower()
    if _YEAR_RE.search(lowered):
        return True
    if any(marker in lowered for marker in _FRESHNESS_MARKERS):
        return True
    return any(marker in lowered for marker in _VOLATILE_MARKERS)


def is_search_eligible(agent_key: str | None, query: str) -> bool:
    """True when ``agent_key`` may search AND ``query`` looks search-worthy.

    Pure + cheap (no I/O) so it can gate before any network call and be unit
    tested directly. Also requires live search to be enabled in settings.
    """
    if not get_settings().web_search_enabled:
        return False
    if agent_key not in SEARCH_ELIGIBLE_AGENTS:
        return False
    lowered = query.lower()
    if _YEAR_RE.search(lowered):
        return True
    return any(cue in lowered for cue in _SEARCH_CUES)


def _normalize(results: list[SearchResult]) -> list[SearchResult]:
    """Trim whitespace and drop hits missing a url or title."""
    cleaned: list[SearchResult] = []
    for r in results:
        url = r.url.strip()
        title = r.title.strip()
        if not url or not title:
            continue
        cleaned.append(
            SearchResult(
                title=title,
                url=url,
                snippet=r.snippet.strip(),
                source=r.source,
            )
        )
    return cleaned


def _dedupe(results: list[SearchResult]) -> list[SearchResult]:
    """Drop repeat hits, keyed by normalized URL then domain+title (stable)."""
    seen: set[str] = set()
    out: list[SearchResult] = []
    for r in results:
        url_key = r.url.rstrip("/").lower()
        title_key = f"{r.domain.lower()}|{r.title.lower()}"
        if url_key in seen or title_key in seen:
            continue
        seen.add(url_key)
        seen.add(title_key)
        out.append(r)
    return out


async def search_outcome(
    query: str, *, limit: int = SEARCH_DEFAULT_LIMIT
) -> SearchOutcome:
    """Query the active provider and report what actually happened.

    Normalize → dedupe → rank → limit, and never raises: a provider fault
    becomes ``FAILED`` rather than an exception, so a search outage can still
    not cost the user a reply. What it can no longer do is masquerade as
    ``NO_RESULTS``.
    """
    cleaned = query.strip()
    if not cleaned or limit <= 0:
        return SearchOutcome(status=SearchStatus.NO_RESULTS, query=cleaned)

    if not is_live():
        # The offline placeholder is installed. Its rows are labelled mocks,
        # and a caller that treats them as evidence relays invented findings.
        return SearchOutcome(status=SearchStatus.UNAVAILABLE, query=cleaned)

    provider = get_provider()
    with langfuse_obs.observe_operation(
        "search.query", input=cleaned, metadata={"limit": limit}
    ) as span:
        try:
            raw = await provider.search(cleaned, limit=limit)
        except SearchProviderError as exc:
            span.update(metadata={"status": SearchStatus.FAILED.value})
            logger.warning("search failed: %s", exc)
            return SearchOutcome(status=SearchStatus.FAILED, query=cleaned)
        except Exception:
            # A provider that raised something outside its contract is a bug,
            # but it is still not evidence — report it as a failure.
            span.update(metadata={"status": SearchStatus.FAILED.value})
            logger.exception("search provider raised unexpectedly")
            return SearchOutcome(status=SearchStatus.FAILED, query=cleaned)
        span.update(metadata={"raw_results": len(raw)})

    with langfuse_obs.observe_operation(
        "search.rank", metadata={"raw_results": len(raw)}
    ) as span:
        ranked = _dedupe(_normalize(raw))[:limit]
        span.update(metadata={"ranked_results": len(ranked)})

    if not ranked:
        return SearchOutcome(status=SearchStatus.NO_RESULTS, query=cleaned)
    return SearchOutcome(status=SearchStatus.AVAILABLE, results=ranked, query=cleaned)


async def search(
    query: str, *, limit: int = SEARCH_DEFAULT_LIMIT
) -> list[SearchResult]:
    """Ranked results, or ``[]``.

    The list-shaped view of :func:`search_outcome`, kept for callers that only
    need the hits. Prefer ``search_outcome`` anywhere the *reason* for an empty
    list changes what should be said.
    """
    return (await search_outcome(query, limit=limit)).results


async def maybe_search(
    agent_key: str | None,
    query: str,
    *,
    limit: int = SEARCH_DEFAULT_LIMIT,
    user_id: uuid.UUID | None = None,
) -> list[SearchResult]:
    """Gate then search: ``[]`` when ineligible/disabled, else ranked results.

    The single entrypoint the reply paths call. Emits the search analytics
    events (best-effort) so search volume + hit rate are observable.
    """
    return (
        await maybe_search_outcome(agent_key, query, limit=limit, user_id=user_id)
    ).results


async def maybe_search_outcome(
    agent_key: str | None,
    query: str,
    *,
    limit: int = SEARCH_DEFAULT_LIMIT,
    user_id: uuid.UUID | None = None,
) -> SearchOutcome:
    """Gate then search, reporting the outcome rather than just the hits.

    An ineligible turn is ``UNAVAILABLE`` when the request actually needed
    current evidence, and ``NO_RESULTS`` when it simply did not warrant a
    search. Those are different things to tell a user, and only the first is
    a reason to withhold an answer.
    """
    if not is_search_eligible(agent_key, query):
        status = (
            SearchStatus.UNAVAILABLE
            if requires_fresh_evidence(query)
            else SearchStatus.NO_RESULTS
        )
        return SearchOutcome(status=status, query=query.strip())

    distinct_id = str(user_id) if user_id else "anonymous"
    analytics.capture_event(
        distinct_id=distinct_id,
        event=analytics.EVENT_SEARCH_PERFORMED,
        properties={"agent": agent_key},
    )
    outcome = await search_outcome(query, limit=limit)
    analytics.capture_event(
        distinct_id=distinct_id,
        event=analytics.EVENT_SEARCH_RESULTS_RETURNED,
        properties={
            "agent": agent_key,
            "count": len(outcome.results),
            "status": outcome.status.value,
        },
    )
    return outcome
