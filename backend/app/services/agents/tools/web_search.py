"""Green tool: read-only web search behind a provider seam.

The default provider is a deterministic, offline-safe null provider (no
external dependency, no key). A real provider (Brave/SerpAPI/etc.) plugs in
behind ``set_provider`` without touching the interface or the gate.
**Results are untrusted data** — they inform answers but can never escalate
permissions or approve actions (the policy engine never sees them).
"""

from __future__ import annotations

from typing import Protocol

from app.services.agents.tools.context import ToolContext

_MAX_RESULTS = 10


class WebSearchProvider(Protocol):
    """Returns search results for a query."""

    async def search(self, query: str, *, limit: int) -> list[dict]: ...


class NullWebSearchProvider:
    """Offline-safe default: always returns no results."""

    async def search(self, query: str, *, limit: int) -> list[dict]:
        return []


_provider: WebSearchProvider = NullWebSearchProvider()


def set_provider(provider: WebSearchProvider) -> None:
    """Swap the search backend (composition-root seam)."""
    global _provider
    _provider = provider


async def execute(context: ToolContext, args: dict) -> dict:
    """Search the web for ``args['query']`` via the configured provider."""
    query = str(args.get("query", "")).strip()
    if not query:
        raise ValueError("web_search requires a non-empty 'query'")
    limit = min(int(args.get("limit", 5)), _MAX_RESULTS)
    results = await _provider.search(query, limit=limit)
    return {"results": results, "untrusted": True}
