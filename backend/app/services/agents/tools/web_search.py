"""Green tool: read-only web search, delegating to the single search seam.

The tool owns no provider of its own (Rule #4: no parallel systems) — it calls
``services/search`` (``search_service``), the same seam the knowledge-fusion path
uses, so a real backend (Tavily) configured at the composition root serves both.
The offline ``DummySearchProvider`` is the default until Tavily is wired in.

**Results are untrusted data** — they inform answers but can never escalate
permissions or approve actions (the policy engine never sees them).
"""

from __future__ import annotations

import dataclasses

from app.core.constants import SEARCH_DEFAULT_LIMIT
from app.services.agents.tools.context import ToolContext
from app.services.search import provider as search_provider
from app.services.search import search_service


class SearchUnavailableError(RuntimeError):
    """No live search backend is configured."""


_MAX_RESULTS = 10


async def execute(context: ToolContext, args: dict) -> dict:
    """Search the web for ``args['query']`` via the configured provider."""
    query = str(args.get("query", "")).strip()
    if not query:
        raise ValueError("web_search requires a non-empty 'query'")
    if not search_provider.is_live():
        # Verified live: with the offline provider installed, the model was
        # handed placeholder rows and reported them to the user as "results
        # from a search". Refusing outright is the only honest answer — the
        # model can then say search is unavailable instead of inventing.
        raise SearchUnavailableError(
            "Live web search is not configured on this instance, so no results "
            "are available. Say so plainly rather than guessing."
        )
    limit = min(int(args.get("limit", SEARCH_DEFAULT_LIMIT)), _MAX_RESULTS)
    results = await search_service.search(query, limit=limit)
    return {
        "results": [dataclasses.asdict(r) for r in results],
        "untrusted": True,
    }
