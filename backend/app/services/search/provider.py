"""Web search provider abstraction + real backends (Phase 3, M8 → M8.5).

A clean seam, by design: callers depend only on the ``SearchProvider`` Protocol,
never on a concrete backend, so a real provider swaps in via ``set_provider`` at
the composition root without any caller change. This is the **single** search
seam for the whole codebase — the ``web_search`` green tool delegates here rather
than carrying its own provider (Rule #4: no parallel systems).

M8.5 ships ``BraveSearchProvider`` (Brave Search REST API, ``BRAVE_API_KEY``) as
the first real backend; the offline ``DummySearchProvider`` remains the default
until the composition root swaps Brave in. **Search results are untrusted data**
— they inform answers and must never escalate permissions or approve actions.
Every provider is best-effort: ``search`` never raises (returns ``[]`` on any
failure), so a search outage can never take down a turn (B10).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlparse

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

# Brave Search REST endpoint (web search). Token goes in the X-Subscription-Token
# header; the response carries hits under ``web.results``.
_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_BRAVE_TIMEOUT_SECONDS = 6.0


@dataclass(frozen=True)
class SearchResult:
    """One search hit: enough to ground or cite an answer."""

    title: str
    url: str
    snippet: str
    # The provider/source name (e.g. "brave", "dummy") — surfaced for citations.
    source: str = ""

    @property
    def domain(self) -> str:
        """The hostname of ``url`` (for compact display), or "" if unparseable."""
        try:
            return urlparse(self.url).netloc
        except ValueError:
            return ""


class SearchProviderError(RuntimeError):
    """The backend was reachable in principle but the query did not succeed.

    Exists so "the provider broke" and "the provider found nothing" stop being
    the same empty list. A caller that cannot tell them apart has to guess, and
    the guess that gets made is "no results" — which reads to the model as a
    settled fact about the world rather than a failure to look.
    """


class SearchProvider(Protocol):
    """Returns ranked results for a query (read-only).

    May raise :class:`SearchProviderError` to report a genuine failure. It must
    not raise anything else — :mod:`search_service` converts an error into a
    ``FAILED`` outcome, and every other exception type would be an unhandled
    bug rather than a search outcome.
    """

    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]: ...


class DummySearchProvider:
    """Offline-safe default: deterministic mock results, no network, no key.

    Returns ``limit`` synthetic results so callers can be wired and tested before
    a real provider is configured. Never raises.
    """

    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        cleaned = query.strip()
        count = max(0, min(limit, 5))
        return [
            SearchResult(
                title=f"Mock result {i + 1} for {cleaned!r}",
                url=f"https://example.com/search?q={cleaned}&r={i + 1}",
                snippet=(
                    f"Placeholder snippet {i + 1}. Configure BRAVE_API_KEY for "
                    "live web results."
                ),
                source="dummy",
            )
            for i in range(count)
        ]


class BraveSearchProvider:
    """Brave Search REST backend (M8.5).

    Calls the Brave web-search API with ``api_key`` (``X-Subscription-Token``)
    and maps ``web.results`` → ``SearchResult``. Best-effort by contract: any
    network error, timeout, non-200, or malformed payload yields ``[]`` so a
    Brave outage degrades gracefully to a search-free turn (B10).
    """

    def __init__(self, api_key: str, *, timeout: float = _BRAVE_TIMEOUT_SECONDS):
        self._api_key = api_key
        self._timeout = timeout

    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        cleaned = query.strip()
        if not cleaned or not self._api_key:
            return []
        # httpx is already a dependency (the Anthropic/OpenAI SDKs use it).
        import httpx

        params: dict[str, str | int] = {
            "q": cleaned,
            "count": max(1, min(limit, 20)),
        }
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self._api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(
                    _BRAVE_ENDPOINT, params=params, headers=headers
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            # Reported, not swallowed. Returning [] here made a timeout
            # indistinguishable from "the web contains nothing about this",
            # and the model presented the second reading to the user.
            #
            # The message deliberately carries the exception type and nothing
            # else: provider error bodies can echo the subscription token back.
            logger.warning("brave search failed: %s", type(exc).__name__)
            raise SearchProviderError(
                f"Brave search failed ({type(exc).__name__})."
            ) from exc
        return self._parse(payload, limit=limit)

    @staticmethod
    def _parse(payload: object, *, limit: int) -> list[SearchResult]:
        """Map a Brave web-search payload to ``SearchResult`` (defensive)."""
        if not isinstance(payload, dict):
            return []
        web = payload.get("web")
        results = web.get("results") if isinstance(web, dict) else None
        if not isinstance(results, list):
            return []
        out: list[SearchResult] = []
        for hit in results:
            if not isinstance(hit, dict):
                continue
            url = str(hit.get("url", "")).strip()
            title = str(hit.get("title", "")).strip()
            if not url or not title:
                continue
            out.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=str(hit.get("description", "")).strip(),
                    source="brave",
                )
            )
            if len(out) >= limit:
                break
        return out


# Process-wide provider; the dummy until the composition root swaps in Brave.
_provider: SearchProvider = DummySearchProvider()


def get_provider() -> SearchProvider:
    """Return the active search provider."""
    return _provider


def is_live() -> bool:
    """True when a real backend is installed (not the offline placeholder).

    The dummy provider exists so callers can be wired and tested before a key
    is configured, and its results are clearly labelled as placeholders. That
    is fine for a knowledge-fusion path that treats search as supplemental —
    but a tool must not report *success* with invented rows, because the model
    then presents them to the user as findings. Tools ask this first and
    return UNAVAILABLE instead.
    """
    return not isinstance(_provider, DummySearchProvider)


def set_provider(provider: SearchProvider) -> None:
    """Swap the search backend (composition-root seam)."""
    global _provider
    _provider = provider


def init_provider(settings: Settings) -> bool:
    """Activate Brave at the composition root when configured. Returns True when
    a live provider is installed; leaves the offline Dummy default otherwise.

    Best-effort: a wiring failure logs and keeps the Dummy default so boot never
    fails over search config.
    """
    try:
        if settings.web_search_enabled and settings.brave_api_key:
            set_provider(BraveSearchProvider(settings.brave_api_key))
            logger.info("web search enabled (Brave)")
            return True
    except Exception:  # pragma: no cover - defensive
        logger.exception("search provider init failed; using offline default")
    logger.info("web search disabled (no BRAVE_API_KEY / flag off)")
    return False
