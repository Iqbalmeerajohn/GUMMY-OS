> **Purpose:** Release notes for **M6.5 — File Intelligence**, the layer that lets
> GUMMY actually *use* uploaded files during conversations.
> **Scope:** File-aware chat (RAG via keyword retrieval), chat attachments,
> multi-source context. Does **not** add embeddings/vector ranking (keyword
> retrieval is the contract; vector RAG is future) or image OCR. **Status:** Shipped.

# M6.5 — File Intelligence

M6 stored files and chunks; M6.5 makes them answerable. GUMMY now retrieves file
content during a turn and answers from uploaded documents — both by keyword
search across all files ("what's in my resume?") and from files attached
directly to a message ("analyze this PDF").

## Architecture

A new read-only service, `file_context_service`, turns a query (+ optional
attachments) into prompt grounding. It feeds the **single** prompt seam
(`prompt_builder.build_prompt(files=...)`), so every reply path becomes
file-aware at once:

```
turn (message [+ attachment_file_ids])
  → file_context_service.retrieve_file_context
      ├─ attachment mode: chunks of the attached files ONLY (ownership-checked)
      └─ search mode:      keyword-retrieve top chunks across all files
  → render_file_context  → {inventory, excerpts}
  → prompt_builder <files> block  (alongside <memory> and <goals>)
  → LLM answers, citing filenames
```

- **Grounded core** (`generate_grounded_reply`, `stream_turn` — the streaming
  path the workspace uses) retrieves file context inline and passes it to the
  prompt builder.
- **Orchestrator path** (`run_turn` default, and the `postTurn` fallback):
  `context_builder.build` packs the retrieved content as `ContextPack.file_context`;
  the general agent renders it via the same `<files>` block. Both paths produce
  identical file grounding.

### Retrieval modes

| Mode | Trigger | Behavior |
| --- | --- | --- |
| **attachment** | turn carries `attachment_file_ids` | uses ONLY those files' chunks; a foreign/missing id → **404** |
| **search** | no attachments | keyword retrieval: OR of `ILIKE` term matches, re-ranked in Python by distinct-term coverage; best-effort (never costs a reply) |

Keyword retrieval is the M6.5 contract (no embeddings) — `file_context_service`
is the seam the future RAG layer swaps a vector retriever under, with no change
to the turn pipeline or prompt builder.

### Multi-source context

The system prompt now unifies three grounding sources, each only when relevant:

```
<memory> … </memory>
<goals> … </goals>
<files>
Uploaded files:
- ResumeGUM.pdf (completed, 12 chunks, uploaded 2026-06-24)
Relevant content from the files:
[ResumeGUM.pdf] …chunk text…
</files>
```

The `<files>` inventory means "what files do I have?" is answerable from the
same block, without retrieving any chunk content.

## File analysis capabilities

No bespoke "tools" — because file content is in the prompt, the existing LLM
handles summarize / explain / extract key points / find projects / find skills /
answer-questions naturally, citing the source filename. Attachments scope the
answer to the chosen document(s).

## API changes

- `POST /api/v1/conversations/{id}/messages` and `…/messages/stream` accept an
  optional `attachment_file_ids: list[uuid]` (≤10) on the turn body. Each id must
  belong to the tenant (foreign → 404). No new endpoints, no migration.

## Chat attachments (frontend)

The workspace composer's paperclip is live: selecting a file uploads it
immediately (reusing the M6 `/files/upload` pipeline), shows a removable chip,
and sends the file id with the next message. `streamTurn` / `postTurn` carry
`attachment_file_ids`; attachments clear after send.

## Observability

Langfuse retrieval spans: `file.attachments` (attachment mode), `file.search`
(keyword mode) — each records retrieved excerpt count and file scope; plus the
existing `file.retrieve_recent` (inventory) on the orchestrator path.

## Safety

Tenant isolation throughout: search and inventory are `user_id`-scoped, and an
attachment id that isn't the tenant's raises 404 (never leaks existence). RLS
remains the backstop in production.

## Out of scope (future)

Vector/semantic ranking (RAG), cross-file synthesis ranking, image OCR,
streaming file uploads on the turn endpoint (attachments upload first, then the
id is referenced — keeps the turn JSON-only).
