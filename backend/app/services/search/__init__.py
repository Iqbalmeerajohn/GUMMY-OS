"""Search provider seam (Phase 3, M8 — prep for M8.5).

Exposes the ``SearchProvider`` abstraction and the offline-safe
``DummySearchProvider`` default. M8 ships **only the seam** — no agent calls it
yet. M8.5 plugs real providers (Brave primary, Tavily fallback) in behind
``set_provider`` without touching callers.
"""

from __future__ import annotations

from app.services.search.provider import (
    DummySearchProvider,
    SearchProvider,
    SearchResult,
    get_provider,
    set_provider,
)

__all__ = [
    "DummySearchProvider",
    "SearchProvider",
    "SearchResult",
    "get_provider",
    "set_provider",
]
