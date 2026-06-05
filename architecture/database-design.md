# GUMMY OS — Database Design

This document defines the core relational data model for GUMMY OS. It is designed to be
**multi-tenant from day one**, **memory-centric**, and **scalable** toward SaaS.

> **Scope:** Logical data model (Phase 0). Types are expressed generically; the
> recommended engine is **PostgreSQL** with **pgvector** for embeddings.

---

## Design Conventions

- **Primary keys:** `id` as `UUID` (globally unique, safe to expose, merge-friendly).
- **Tenancy:** every domain table carries `user_id` (FK → `users.id`). An
  `organization_id` is added in Phase 14 for business multi-tenancy.
- **Timestamps:** `created_at` and `updated_at` (UTC) on every table.
- **Soft deletes:** `deleted_at` (nullable) where user-recoverable data matters.
- **Flexible metadata:** a `metadata JSONB` column on most tables for forward-compatible
  attributes without migrations.
- **Embeddings:** stored as `vector` (pgvector) alongside the source text for hybrid
  (vector + relational) retrieval.
- **Indexing:** FKs indexed; `user_id` indexed everywhere; vector columns use an
  ANN index (e.g. HNSW/IVFFlat).

### Entity Relationship Overview

```
users (1) ──< (∞) conversations (1) ──< (∞) messages
  │
  ├──< (∞) memories
  ├──< (∞) documents ──< (∞) document_chunks   (chunks implied by ingestion)
  ├──< (∞) jobs
  ├──< (∞) research_reports
  └──1  settings  (one row per user)

messages, documents, jobs, research_reports may each generate memories
(via the memory pipeline).  conversations link agents' work back to context.
```

---

## 1. `users`

The account and identity at the center of every record. The root of tenancy.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID (PK) | Unique user identifier. |
| `email` | TEXT (unique) | Login identity. |
| `password_hash` | TEXT | Hashed credential (null if external auth/OAuth). |
| `full_name` | TEXT | Display name. |
| `avatar_url` | TEXT | Optional profile image (object storage). |
| `auth_provider` | TEXT | `local`, `google`, etc. |
| `status` | TEXT | `active`, `suspended`, `deleted`. |
| `last_login_at` | TIMESTAMPTZ | For activity/security. |
| `metadata` | JSONB | Extensible profile attributes. |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |
| `deleted_at` | TIMESTAMPTZ (nullable) | Soft delete. |

**Relationships:** one user → many conversations, memories, documents, jobs,
research_reports; one user → one settings row. **This is the parent of everything.**

---

## 2. `conversations`

A thread of interaction between the user and the system (short-term memory container).

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID (PK) | |
| `user_id` | UUID (FK → users.id) | Owner. |
| `title` | TEXT | Auto-generated or user-set summary. |
| `agent` | TEXT | Primary agent/context (e.g. `career`, `research`, `orchestrator`). |
| `summary` | TEXT | Rolling compacted summary for long threads. |
| `status` | TEXT | `active`, `archived`. |
| `last_message_at` | TIMESTAMPTZ | For sorting/recency. |
| `metadata` | JSONB | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |
| `deleted_at` | TIMESTAMPTZ (nullable) | |

**Relationships:** belongs to one user; has many messages. The `summary` field supports
context compaction described in the memory architecture.

---

## 3. `messages`

A single turn within a conversation — the atomic unit of dialogue.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID (PK) | |
| `conversation_id` | UUID (FK → conversations.id) | Parent thread. |
| `user_id` | UUID (FK → users.id) | Denormalized for fast tenant queries. |
| `role` | TEXT | `user`, `assistant`, `system`, `tool`. |
| `agent` | TEXT | Which agent produced an assistant message. |
| `content` | TEXT | Message body. |
| `tool_calls` | JSONB | Tool invocations/results, if any. |
| `tokens` | INTEGER | Token count (cost/observability). |
| `model` | TEXT | LLM used for this message. |
| `metadata` | JSONB | |
| `created_at` | TIMESTAMPTZ | |

**Relationships:** belongs to one conversation and one user. Indexed by
`(conversation_id, created_at)` for fast ordered retrieval. Messages are a primary
source for the memory-capture pipeline.

---

## 4. `memories`

The long-term semantic memory — the moat. Durable facts, preferences, summaries, and
knowledge, embedded for semantic recall.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID (PK) | |
| `user_id` | UUID (FK → users.id) | Owner. |
| `type` | TEXT | `fact`, `preference`, `summary`, `episodic`, `semantic`. |
| `content` | TEXT | The memory text. |
| `embedding` | VECTOR | Embedding for similarity search (pgvector). |
| `importance` | REAL | Ranking weight (0–1) for prioritization. |
| `confidence` | REAL | How sure the system is (0–1). |
| `source_type` | TEXT | Origin: `message`, `document`, `job`, `research_report`. |
| `source_id` | UUID (nullable) | Polymorphic pointer to the originating row. |
| `last_recalled_at` | TIMESTAMPTZ | For recency/decay. |
| `metadata` | JSONB | Tags, entities, etc. |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |
| `deleted_at` | TIMESTAMPTZ (nullable) | Supports "forgetting". |

**Relationships:** belongs to one user; loosely links back to any source record via
`(source_type, source_id)`. **Read by every agent on every request** via the Memory
Service's hybrid retrieval.

---

## 5. `documents`

Files the user ingests (PDFs, notes, etc.). Parsed, chunked, and embedded for retrieval.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID (PK) | |
| `user_id` | UUID (FK → users.id) | Owner. |
| `title` | TEXT | Display name. |
| `file_url` | TEXT | Location in object storage. |
| `mime_type` | TEXT | `application/pdf`, etc. |
| `size_bytes` | BIGINT | |
| `status` | TEXT | `uploaded`, `processing`, `indexed`, `failed`. |
| `content_text` | TEXT | Extracted full text (optional). |
| `chunk_count` | INTEGER | Number of embedded chunks. |
| `metadata` | JSONB | Source, author, tags. |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |
| `deleted_at` | TIMESTAMPTZ (nullable) | |

> **Companion table `document_chunks`** (implied by the ingestion pipeline):
> `id`, `document_id` (FK), `user_id`, `chunk_index`, `content`, `embedding VECTOR`,
> `metadata`, `created_at`. Chunks are what vector search actually queries.

**Relationships:** belongs to one user; has many chunks; chunks/documents feed
`memories`. Drives the document-memory tier.

---

## 6. `jobs`

The Career Agent's pipeline: tracked job opportunities and applications.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID (PK) | |
| `user_id` | UUID (FK → users.id) | Owner. |
| `title` | TEXT | Job title. |
| `company` | TEXT | Employer. |
| `location` | TEXT | Including remote. |
| `source_url` | TEXT | Where it was found. |
| `description` | TEXT | Full posting. |
| `status` | TEXT | `saved`, `applied`, `interviewing`, `offer`, `rejected`, `closed`. |
| `application_data` | JSONB | Tailored resume ref, cover letter, answers. |
| `match_score` | REAL | Fit score (0–1) computed against the user's profile. |
| `applied_at` | TIMESTAMPTZ | When applied. |
| `metadata` | JSONB | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |
| `deleted_at` | TIMESTAMPTZ (nullable) | |

**Relationships:** belongs to one user; produced/updated by the Career Agent; can
generate `memories` (e.g. "applied to X", interview notes).

---

## 7. `research_reports`

The Research Agent's structured, reusable outputs.

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID (PK) | |
| `user_id` | UUID (FK → users.id) | Owner. |
| `conversation_id` | UUID (FK → conversations.id, nullable) | Originating thread. |
| `topic` | TEXT | Research subject/question. |
| `summary` | TEXT | Executive summary. |
| `content` | TEXT | Full structured report (markdown). |
| `sources` | JSONB | Citations: URLs, titles, snippets. |
| `status` | TEXT | `pending`, `in_progress`, `completed`, `failed`. |
| `embedding` | VECTOR | For semantic recall of past research. |
| `metadata` | JSONB | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |
| `deleted_at` | TIMESTAMPTZ (nullable) | |

**Relationships:** belongs to one user; optionally tied to a conversation; feeds
`memories`, the Learning Agent, and the Builder Agent.

---

## 8. `settings`

Per-user configuration and personalization (one row per user).

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID (PK) | |
| `user_id` | UUID (FK → users.id, unique) | One settings row per user. |
| `preferred_model` | TEXT | Default LLM (e.g. a Claude model id). |
| `personality` | JSONB | Tone/voice config (Personality Layer, Phase 8). |
| `enabled_agents` | JSONB | Which agents are active for this user. |
| `notification_prefs` | JSONB | Email/push/proactive nudge settings. |
| `privacy_prefs` | JSONB | Memory retention, data-sharing choices. |
| `integrations` | JSONB | Connected accounts (encrypted token refs). |
| `usage_limits` | JSONB | Cost/usage caps. |
| `locale` | TEXT | Language/timezone. |
| `metadata` | JSONB | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

**Relationships:** one-to-one with `users`. Read by the Orchestrator and every agent to
personalize behavior. Sensitive integration tokens are stored as **encrypted
references**, not raw secrets.

---

## Relationship Summary

| From | Relationship | To |
| --- | --- | --- |
| `users` | 1 → ∞ | `conversations`, `memories`, `documents`, `jobs`, `research_reports` |
| `users` | 1 → 1 | `settings` |
| `conversations` | 1 → ∞ | `messages` |
| `conversations` | 1 → ∞ (nullable) | `research_reports` |
| `documents` | 1 → ∞ | `document_chunks` (ingestion) |
| `messages`/`documents`/`jobs`/`research_reports` | source → | `memories` (via `source_type` + `source_id`) |

---

## Scalability & Integrity Notes

- **Tenant scoping + RLS:** `user_id` on every table enables PostgreSQL row-level
  security as defense-in-depth for SaaS multi-tenancy.
- **Hybrid retrieval:** relational filters (`user_id`, `type`, recency) combine with
  vector similarity (`embedding`) for precise, fast, *private* recall.
- **JSONB everywhere appropriate:** evolve the schema without constant migrations.
- **Soft deletes + audit:** user-recoverable data and an action audit trail support
  privacy guarantees (export/delete) and accountability.
- **Partition-ready:** high-volume tables (`messages`, `memories`, `document_chunks`)
  can be partitioned by `user_id`/time as the system grows.
- **Phase 14 evolution:** introduce `organizations` and `organization_id` to extend
  tenancy from individuals to businesses without redesigning the core model.

---

_This model backs the architecture in [system-design.md](system-design.md) and the
phased plan in [../docs/ROADMAP.md](../docs/ROADMAP.md)._
