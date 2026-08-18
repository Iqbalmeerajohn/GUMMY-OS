"""Green tools: search and inventory the user's own uploaded files.

Both delegate to the existing file services rather than reimplementing search —
``file_retrieval_service`` for chunk lookup and ``file_repository`` for the
inventory. There is one file-search implementation in this codebase and these
tools are callers of it, not a second copy.

Tenant scoping is not optional and not the model's business: ``user_id`` comes
from :class:`ToolContext`, which the executor builds from the authenticated
request. Nothing in the tool arguments can widen it, so a model that asks for
another user's files simply searches its own.
"""

from __future__ import annotations

from app.repositories import file_repository as file_repo
from app.services.agents.tools.context import ToolContext
from app.services.files.file_retrieval_service import file_retrieval_service

_MAX_RESULTS = 8
_MAX_EXCERPT_CHARS = 600
_MAX_INVENTORY = 50


async def execute(context: ToolContext, args: dict) -> dict:
    """Search the content of the user's indexed files for ``args['query']``."""
    query = str(args.get("query", "")).strip()
    if not query:
        raise ValueError("file_search requires a non-empty 'query'")
    limit = max(1, min(int(args.get("limit", 5)), _MAX_RESULTS))

    chunks = await file_retrieval_service.search_chunks(
        context.session,
        user_id=context.user_id,
        query=query,
        limit=limit,
    )
    results = [
        {
            # Provenance travels with every excerpt so the answer can cite the
            # file it came from rather than asserting it unattributed.
            "filename": chunk.file.original_filename if chunk.file else "unknown",
            "file_id": str(chunk.file_id),
            "chunk_index": chunk.chunk_index,
            "excerpt": chunk.content[:_MAX_EXCERPT_CHARS],
        }
        for chunk in chunks
    ]
    return {"query": query, "match_count": len(results), "results": results}


async def execute_list(context: ToolContext, args: dict) -> dict:
    """List the user's files, so "do I have X?" is answerable from fact.

    Without this the model can only guess whether a file exists, and a confident
    guess about someone's own documents is the worst possible answer.
    """
    files, total = await file_repo.list_files(
        context.session, user_id=context.user_id, limit=_MAX_INVENTORY, offset=0
    )
    return {
        "total": total,
        "files": [
            {
                "filename": f.original_filename,
                "file_id": str(f.id),
                "mime_type": f.mime_type,
                "size_bytes": f.size_bytes,
                "uploaded_at": f.created_at.isoformat() if f.created_at else None,
                "processing_status": f.processing_status.value,
                "indexed": f.processing_status.value == "processed",
            }
            for f in files
        ],
    }
