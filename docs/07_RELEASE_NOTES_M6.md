> **Purpose:** Release notes for **M6 — Files System**, the foundational file
> knowledge layer of GUMMY OS.
> **Scope:** Covers what M6 ships (upload, storage, extraction, chunking,
> retrieval, agent awareness, dashboard/workspace UI, observability) and how it
> is wired. Does **not** cover vector search / RAG ranking (future) or image OCR
> (explicitly out of scope). **Status:** Shipped.

# M6 — Files System

Users can upload files into GUMMY OS, and those files become part of the user's
long-term knowledge system. This is a complete file-management layer — not just
blob storage — and is the substrate future phases (RAG, Research/Career/Learning
agents, Workspace) build on.

## Architecture

```
upload (multipart)
  → validate (size / MIME)              [file_service.upload_file]
  → store bytes (provider-agnostic)     [FileStorage.save  → file.upload span]
  → create File row (upload_status=uploaded)
  → extract text                        [extraction_service → file.process span]
  → chunk deterministically             [chunking_service  → file.chunk span]
  → store FileChunk rows (processing_status=completed)
```

Two **independent** lifecycles per file:

- `upload_status` — the bytes (`pending → uploaded → failed`).
- `processing_status` — the knowledge extraction (`pending → processing →
  completed | failed`).

A *validation* failure (size/type) raises before anything is stored. A
*processing* failure (corrupt PDF, missing parser) is captured to Sentry and
recorded on the file (`processing_status=failed` + `error_message`) — the upload
still succeeds, so bytes are never lost and processing can be retried.

Chunking is **deterministic** (fixed-size overlapping character windows): the
same input always yields the same chunks, so they are a stable substrate the RAG
layer can embed and re-embed without drift.

### Seams (no vendor lock-in)

- **Storage** — `FileStorage` protocol (`build_key/save/load/delete`).
  `LocalFileStorage` ships today; `supabase`/`r2`/`s3` plug in at
  `files/storage/factory.py` only (mirrors the embeddings/LLM factories).
- **Retrieval** — `FileRetrievalService` (metadata, paginated chunks, keyword
  chunk search). Keyword-only by design; vector ranking is the future RAG layer.

## Database

- `files` — `id, user_id, filename, original_filename, mime_type, size_bytes,
  storage_path, upload_status, processing_status, chunk_count, error_message,
  created_at, updated_at`.
- `file_chunks` — `id, user_id, file_id, chunk_index, content, token_count,
  metadata_json, created_at`. `file_id` is `ON DELETE CASCADE`.

Both tables: denormalized `user_id`, fail-closed direct-column **RLS**, the
conditional `gummy_app` grant, and CHECK constraints on the status enums.
Migration `0021_add_files` (down_revision `0020_add_goal_milestones`).

## API (`/api/v1/files`)

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/files/upload` | Upload a file (multipart) → processed `FileResponse` |
| GET | `/files` | Paginated list (newest first) |
| GET | `/files/stats` | Total count + recent files (dashboard) |
| GET | `/files/{id}` | File metadata |
| GET | `/files/{id}/chunks` | Paginated chunks (RAG prep) |
| DELETE | `/files/{id}` | Delete file bytes + row (cascades chunks) |

All routes are tenant-scoped; foreign tenants see `404`, never `403`.

## Supported types

PDF, TXT, MD, DOCX (MVP) + CSV, XLSX (cheap extras). Parsers (`pypdf`,
`python-docx`, `openpyxl`) are imported lazily, only when that format is
uploaded. **Image OCR is intentionally not implemented.**

## Agent awareness

Active agents see uploaded-file **metadata only** (filename, MIME type,
processing status, chunk count) via the context pack — never file content. The
lookup uses the same SAVEPOINT degrade-to-empty guard as goals, so a files-table
outage can never take a turn down. This is the seam future agent file-selection
logic builds on.

## Observability

- **Langfuse** spans: `file.upload`, `file.process`, `file.chunk` (filename,
  mime type, size, extracted chars, chunk count, duration); plus
  `file.search_chunks` and `file.retrieve_recent`.
- **Sentry**: processing failures captured (`component=file_processing`),
  best-effort storage-delete failures (`component=file_delete`).
- **PostHog** (frontend, existing analytics seam): `file_uploaded`,
  `file_processed`, `file_deleted`.

## Frontend

- **Files page** (`/files`) — drag-and-drop / click upload, file list with
  processing-status badges, size/chunk/age, and delete.
- **Dashboard** — `Files` widget (recent files + total), auto-updating via
  TanStack Query invalidation.
- **Navigation** — Files added to the desktop header and mobile bottom nav.

## Configuration

- `FILES_STORAGE_PROVIDER` (default `local`)
- `FILES_STORAGE_DIR` (default `var/files`; point at a mounted volume on Railway)

## Out of scope (future)

Vector search / RAG ranking, image OCR, async/queue-based processing (M6
processes synchronously in-request; the pipeline is structured so a worker can
take over without API changes).
