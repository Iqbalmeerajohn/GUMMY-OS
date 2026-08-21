"""Search provider seam (Phase 3, M8 → M8.5).

The single search seam for the codebase: the ``SearchProvider`` abstraction, the
offline-safe ``DummySearchProvider`` default, and the real ``TavilySearchProvider``
(M8.5). Real backends swap in behind ``set_provider`` at the composition root
without touching callers; the ``web_search`` green tool and the knowledge-fusion
path both consume this seam.
"""

from __future__ import annotations

from app.services.search.provider import (
    DummySearchProvider,
    SearchProvider,
    SearchProviderError,
    SearchResult,
    TavilySearchProvider,
    get_provider,
    set_provider,
)

__all__ = [
    "TavilySearchProvider",
    "DummySearchProvider",
    "SearchProvider",
    "SearchProviderError",
    "SearchResult",
    "get_provider",
    "set_provider",
]
