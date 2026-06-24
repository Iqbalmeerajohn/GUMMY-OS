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
    ``search.summarize``) + PostHog (``SearchPerformed`` / ``SearchResultsReturned``).

Best-effort by contract: every entrypoint returns ``[]`` rather than raising, so
a search outage never costs the user a reply (B10).
"""

from __future__ import annotations

import logging
import re
import uuid

from app.core.config import get_settings
from app.core.constants import SEARCH_DEFAULT_LIMIT
from app.observability import analytics
from app.observability import langfuse as langfuse_obs
from app.services.search.provider import SearchResult, get_provider

logger = logging.getLogger(__name__)

# Specialists allowed to spend on live search (B4/B5/B6). Memory/Planner/General
# answer from the user's own knowledge and never hit the network.
SEARCH_ELIGIBLE_AGENTS: frozenset[str] = frozenset(
    {"research", "career", "learning"}
)

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


async def search(
    query: str, *, limit: int = SEARCH_DEFAULT_LIMIT
) -> list[SearchResult]:
    """Query the active provider, then normalize → dedupe → rank → limit.

    Never raises: the provider is best-effort, and any unexpected fault degrades
    to ``[]``. Ranking is the provider's order preserved through dedupe (the
    backend already returns relevance-ordered hits); the seam is here for a
    smarter re-rank later without touching callers.
    """
    cleaned = query.strip()
    if not cleaned or limit <= 0:
        return []
    provider = get_provider()
    with langfuse_obs.observe_operation(
        "search.query", input=cleaned, metadata={"limit": limit}
    ) as span:
        try:
            raw = await provider.search(cleaned, limit=limit)
        except Exception:
            logger.warning("search provider raised; degrading to []", exc_info=True)
            raw = []
        span.update(metadata={"raw_results": len(raw)})

    with langfuse_obs.observe_operation(
        "search.rank", metadata={"raw_results": len(raw)}
    ) as span:
        ranked = _dedupe(_normalize(raw))[:limit]
        span.update(metadata={"ranked_results": len(ranked)})
    return ranked


async def maybe_search(
    agent_key: str | None,
    query: str,
    *,
    limit: int = SEARCH_DEFAULT_LIMIT,
    user_id: uuid.UUID | None = None,
) -> list[SearchResult]:
    """Gate then search: ``[]`` when ineligible/disabled, else ranked results.

    The single entrypoint the reply paths call. Emits the PostHog search events
    (best-effort) so search volume + hit rate are observable.
    """
    if not is_search_eligible(agent_key, query):
        return []
    distinct_id = str(user_id) if user_id else "anonymous"
    analytics.capture_event(
        distinct_id=distinct_id,
        event=analytics.EVENT_SEARCH_PERFORMED,
        properties={"agent": agent_key},
    )
    results = await search(query, limit=limit)
    analytics.capture_event(
        distinct_id=distinct_id,
        event=analytics.EVENT_SEARCH_RESULTS_RETURNED,
        properties={"agent": agent_key, "count": len(results)},
    )
    return results
