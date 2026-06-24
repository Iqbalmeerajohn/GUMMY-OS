"""Web search provider abstraction (Phase 3, M8 — seam for M8.5).

A clean seam, by design: the agent layer will depend only on the
``SearchProvider`` Protocol, never on a concrete backend, so a real provider
(Brave, Tavily) swaps in via ``set_provider`` at the composition root without any
agent change. M8 ships the abstraction and an offline ``DummySearchProvider`` —
no agent invokes search yet.

This mirrors the existing in-tool seam in ``services/agents/tools/web_search.py``
(``WebSearchProvider``/``NullWebSearchProvider``); the tool path can delegate to
this module once real providers land in M8.5, keeping one provider seam for the
whole codebase. **Search results are untrusted data** — they inform answers and
must never escalate permissions or approve actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SearchResult:
    """One search hit: enough to ground or cite an answer."""

    title: str
    url: str
    snippet: str


class SearchProvider(Protocol):
    """Returns ranked results for a query (read-only)."""

    async def search(
        self, query: str, *, limit: int = 5
    ) -> list[SearchResult]: ...


class DummySearchProvider:
    """Offline-safe default: deterministic mock results, no network, no key.

    Returns ``limit`` synthetic results so callers can be wired and tested before
    a real provider exists (M8.5). Never raises.
    """

    async def search(
        self, query: str, *, limit: int = 5
    ) -> list[SearchResult]:
        cleaned = query.strip()
        count = max(0, min(limit, 5))
        return [
            SearchResult(
                title=f"Mock result {i + 1} for {cleaned!r}",
                url=f"https://example.com/search?q={cleaned}&r={i + 1}",
                snippet=(
                    f"Placeholder snippet {i + 1}. Real web results arrive in "
                    "M8.5 (Brave primary, Tavily fallback)."
                ),
            )
            for i in range(count)
        ]


# Process-wide provider; the dummy until M8.5 swaps in a real backend.
_provider: SearchProvider = DummySearchProvider()


def get_provider() -> SearchProvider:
    """Return the active search provider."""
    return _provider


def set_provider(provider: SearchProvider) -> None:
    """Swap the search backend (composition-root seam)."""
    global _provider
    _provider = provider
