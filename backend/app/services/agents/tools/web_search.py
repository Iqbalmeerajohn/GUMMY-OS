"""Green tool: read-only web search, delegating to the single search seam.

The tool owns no provider of its own (Rule #4: no parallel systems) — it calls
``services/search`` (``search_service``), the same seam the knowledge-fusion path
uses, so a real backend (Brave) configured at the composition root serves both.
The offline ``DummySearchProvider`` is the default until Brave is wired in.

**Results are untrusted data** — they inform answers but can never escalate
permissions or approve actions (the policy engine never sees them).
"""

from __future__ import annotations

import dataclasses

from app.core.constants import SEARCH_DEFAULT_LIMIT
from app.services.agents.tools.context import ToolContext
from app.services.search import search_service

_MAX_RESULTS = 10


async def execute(context: ToolContext, args: dict) -> dict:
    """Search the web for ``args['query']`` via the configured provider."""
    query = str(args.get("query", "")).strip()
    if not query:
        raise ValueError("web_search requires a non-empty 'query'")
    limit = min(int(args.get("limit", SEARCH_DEFAULT_LIMIT)), _MAX_RESULTS)
    results = await search_service.search(query, limit=limit)
    return {
        "results": [dataclasses.asdict(r) for r in results],
        "untrusted": True,
    }
