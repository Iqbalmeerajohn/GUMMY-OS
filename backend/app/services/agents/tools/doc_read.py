"""Green tool: read one of the user's own documents.

This was a stub — declared, gated and audited, but resolving nothing, because
the document store arrived after the tool did. The store exists now, so the
tool reads from it.

Resolution is by filename rather than id. A model that has just run
``file_list`` or ``file_search`` knows a document as "Resume.pdf", not as a
UUID, and asking it to carry an opaque identifier between tool calls is how
identifiers end up in the user's answer. Matching is case-insensitive and
accepts a substring, because a model asked about "my resume" will say exactly
that.

Ownership is enforced by the query, not by the argument: ``user_id`` comes from
:class:`ToolContext`, so a filename belonging to someone else resolves to
nothing rather than to their document.
"""

from __future__ import annotations

from app.repositories import file_chunk_repository as chunk_repo
from app.repositories import file_repository as file_repo
from app.services.agents.tools.context import ToolContext

# A document read is for grounding an answer, not for reproducing the file. The
# cap keeps a 200-page PDF from consuming the whole context window and pushing
# out the conversation it was meant to support.
_MAX_CHARS = 6000
_MAX_CHUNKS = 12


async def execute(context: ToolContext, args: dict) -> dict:
    """Read a document the user owns, identified by filename."""
    ref = str(args.get("ref", "")).strip()
    if not ref:
        raise ValueError("doc_read requires a non-empty 'ref'")

    files, _ = await file_repo.list_files(
        context.session, user_id=context.user_id, limit=100, offset=0
    )
    needle = ref.lower()
    match = next(
        (f for f in files if needle in f.original_filename.lower()),
        None,
    )
    if match is None:
        # Reported as data, not raised: "you have no such document" is a real
        # answer, and the model should say it rather than treat it as an error.
        return {"found": False, "ref": ref, "content": None}

    chunks, _ = await chunk_repo.list_for_file(
        context.session,
        file_id=match.id,
        user_id=context.user_id,
        limit=_MAX_CHUNKS,
        offset=0,
    )

    sections: list[str] = []
    used = 0
    for chunk in chunks:
        meta = chunk.metadata_json or {}
        page, section = meta.get("page"), meta.get("section")
        label = f"page {page}" if page is not None else (section or "")
        body = chunk.content
        if used + len(body) > _MAX_CHARS:
            body = body[: max(0, _MAX_CHARS - used)]
        if not body:
            break
        sections.append(f"[{label}] {body}" if label else body)
        used += len(body)
        if used >= _MAX_CHARS:
            break

    return {
        "found": True,
        "filename": match.original_filename,
        "searchable": match.indexed_at is not None,
        "chunk_count": match.chunk_count,
        "truncated": used >= _MAX_CHARS,
        "content": "\n\n".join(sections),
    }
