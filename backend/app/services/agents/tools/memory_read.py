"""Green tool: read-only hybrid retrieval over the user's memories."""

from __future__ import annotations

from app.core.constants import DEFAULT_RETRIEVAL_LIMIT, MAX_RETRIEVAL_LIMIT
from app.services.agents.tools.context import ToolContext
from app.services.memory import memory_retrieval_service


async def execute(context: ToolContext, args: dict) -> dict:
    """Retrieve ranked memories for ``args['query']`` (tenant-scoped)."""
    if context.embedding_service is None:
        raise ValueError("memory_read requires an embedding service")
    query = str(args.get("query", "")).strip()
    if not query:
        raise ValueError("memory_read requires a non-empty 'query'")
    limit = min(int(args.get("limit", DEFAULT_RETRIEVAL_LIMIT)), MAX_RETRIEVAL_LIMIT)
    ranked = await memory_retrieval_service.retrieve_memories(
        context.session,
        user_id=context.user_id,
        query=query,
        embedding_service=context.embedding_service,
        limit=limit,
    )
    return {
        "memories": [
            {
                "content": item.memory.content,
                "category": item.memory.category.value,
                "score": item.final_score,
            }
            for item in ranked
        ]
    }
