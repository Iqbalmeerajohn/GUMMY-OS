"""Green tool: read a stored document (modeled; store arrives later).

The document store is a future phase; until then this executor resolves
nothing — but the tool is real: declared, gated, audited, and contract-
stable, so document-reading agents need no framework change later.
"""

from __future__ import annotations

from app.services.agents.tools.context import ToolContext


async def execute(context: ToolContext, args: dict) -> dict:
    """Read a document by reference. Always not-found until the store ships."""
    ref = str(args.get("ref", "")).strip()
    if not ref:
        raise ValueError("doc_read requires a non-empty 'ref'")
    return {"found": False, "ref": ref, "content": None}
