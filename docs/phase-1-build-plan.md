# GUMMY OS — Phase 1 Build Plan: The Memory Engine

> **Purpose:** The implementation blueprint for Phase 1 — the persistent, consent-based
> long-term memory that every agent depends on. *Design only; no application code yet.*

> **Scope:** Backend memory engine on FastAPI + PostgreSQL/pgvector + Claude. Realizes
> [memory-system.md](../architecture/memory-system.md),
> [database-design.md](../architecture/database-design.md), and
> [system-design.md](../architecture/system-design.md). **Status:** Planned (entering build).
> **Authors:** Lead Backend Architect / Senior AI Systems Engineer.

> **Refinement vs. Phase 0:** embeddings move from an inline `memories.embedding` column to
> a dedicated `memory_embeddings` table — to support re-embedding, multiple/upgraded models,
> and a lean hot row. This is the only intentional divergence from
> [database-design.md](../architecture/database-design.md) and is recorded here as the
> source of truth for Phase 1.

---

## 1. Backend Folder Structure

A layered (clean-architecture) backend. The dependency rule points inward:
**`api → services → repositories → database`**. API never touches SQL; services never build
HTTP responses. This keeps the Memory Service a swappable, testable core (the moat) rather
than logic smeared across route handlers.

```
backend/
├── app/
│   ├── main.py                     # FastAPI app factory, lifespan (db/LLM warmup), router mount
│   ├── api/
│   │   ├── deps.py                 # shared deps: current_user (JWT), db session, pagination
│   │   ├── router.py               # aggregates all v1 routers under /api/v1
│   │   └── v1/
│   │       ├── health.py           # liveness/readiness
│   │       ├── memories.py         # memory CRUD + lifecycle (archive/forget)
│   │       ├── memory_versions.py  # version history + supersession chain
│   │       ├── retrieval.py        # /recall + /context (the read path)
│   │       ├── documents.py        # upload + ingestion status
│   │       ├── resumes.py          # resume versions + comparison
│   │       ├── conversations.py    # threads (memory-capture source)
│   │       ├── messages.py         # turns within a thread
│   │       └── settings.py         # consent mode, pause-memory switch
│   ├── core/
│   │   ├── config.py               # Pydantic Settings, loaded from env (.env.example)
│   │   ├── security.py             # Supabase JWT verification, tenant guard, RLS GUC set
│   │   ├── logging.py              # structured JSON logging
│   │   ├── exceptions.py           # typed errors + FastAPI exception handlers
│   │   └── constants.py            # enums, category names, scoring weights, token budgets
│   ├── database/
│   │   ├── session.py              # async engine, pooled session factory (Supabase pooler)
│   │   ├── base.py                 # declarative base + shared mixins (timestamps, soft-delete)
│   │   └── migrations/             # Alembic env + versioned migrations
│   ├── models/                     # SQLAlchemy ORM (one file per table)
│   │   ├── user.py
│   │   ├── memory.py
│   │   ├── memory_version.py
│   │   ├── memory_embedding.py
│   │   ├── conversation.py
│   │   ├── message.py
│   │   ├── document.py
│   │   ├── document_chunk.py
│   │   ├── resume.py
│   │   └── resume_version.py
│   ├── schemas/                    # Pydantic DTOs (request/response contracts)
│   │   ├── common.py               # pagination, error envelope, ids
│   │   ├── memory.py
│   │   ├── retrieval.py            # query in, ranked context-pack out
│   │   ├── resume.py
│   │   └── document.py
│   ├── repositories/               # data-access layer: queries only, no business rules
│   │   ├── memory_repo.py          # hybrid search SQL lives here
│   │   ├── embedding_repo.py
│   │   ├── version_repo.py
│   │   ├── document_repo.py
│   │   └── resume_repo.py
│   ├── services/                   # business logic (the brain)
│   │   ├── memory/
│   │   │   ├── memory_service.py   # public facade every agent will call
│   │   │   ├── capture.py          # classify → score → dedupe → supersede → persist
│   │   │   ├── scoring.py          # importance_score + confidence_score
│   │   │   ├── categorizer.py      # assign one of the 7 categories
│   │   │   ├── retrieval.py        # hybrid search + weighted ranking + MMR diversity
│   │   │   └── lifecycle.py        # update/archive/delete/forget state machine
│   │   ├── embeddings/
│   │   │   └── embedding_service.py# provider-abstracted; batch + cache + content-hash
│   │   ├── llm/
│   │   │   └── llm_gateway.py      # Claude wrapper: tiered models, prompt caching, retries
│   │   ├── documents/
│   │   │   └── ingestion.py        # parse → chunk → embed → index → derive memories
│   │   ├── resume/
│   │   │   └── resume_service.py   # versioning + structured diff + Career-memory sync
│   │   └── context/
│   │       └── context_assembler.py# token-budgeted, category-grouped context pack
│   ├── workers/                    # async/background (keep request path fast)
│   │   ├── queue.py                # job enqueue/abstraction (Redis/RQ or in-proc early)
│   │   └── tasks.py                # embed, ingest, summarize/compact, reinforce
│   └── utils/
│       ├── tokens.py               # token counting + budget math
│       ├── text.py                 # normalization, chunking, hashing
│       └── time.py                 # UTC helpers, recency/decay math
├── tests/
│   ├── unit/                       # scoring, ranking, dedupe, diff (pure logic)
│   ├── integration/                # DB + pgvector + endpoints (testcontainers/Supabase)
│   └── conftest.py                 # fixtures: db, seeded user, fake embedder/LLM
├── alembic.ini
├── pyproject.toml                  # uv-managed; Ruff/Black/mypy/pytest config
├── Dockerfile
├── .dockerignore
└── README.md
```

**Layer responsibilities**

| Layer | Owns | Must NOT |
| --- | --- | --- |
| `api/` | HTTP shape, auth dependency, validation, status codes | Contain business logic or SQL |
| `schemas/` | The typed wire contract (Pydantic in/out) | Leak ORM models to clients |
| `services/` | All decisions: scoring, dedupe, ranking, lifecycle, consent | Build HTTP responses or hand-write SQL |
| `repositories/` | Queries, transactions, hybrid-search SQL | Make business decisions |
| `models/` | Table mapping + relationships | Hold logic beyond simple properties |
| `core/` | Config, auth, logging, errors, constants | Import services (no cycles) |
| `workers/` | Async embed/ingest/compaction off the request path | Be required for a read to succeed |

> **Why repositories *and* models?** The hybrid retrieval query (vector + filters +
> full-text) is the riskiest, most-tuned SQL in the system. Isolating it in
> `memory_repo.py` lets us optimize/swap pgvector → Qdrant later without touching services
> — exactly the swappable seam the conventions demand.

---

## 2. Memory Database Design

Four core tables for Phase 1, all **tenant-scoped (`user_id`)**, UUID PKs, UTC timestamps,
soft-delete where data is user-recoverable, **RLS enabled** as defense-in-depth.

### 2.1 `users`
The tenancy root (subset of the full model in
[database-design.md](../architecture/database-design.md); Supabase Auth is the identity
provider, this row is our source of truth).

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | Matches the Supabase Auth user id. |
| `email` | TEXT UNIQUE | Login identity. |
| `full_name` | TEXT | Display name. |
| `auth_provider` | TEXT | `local`, `google`, … |
| `consent_mode` | TEXT | `explicit` \| `assisted` \| `autonomous` (default `assisted`). |
| `memory_paused` | BOOLEAN | Global kill-switch for new writes (default `false`). |
| `status` | TEXT | `active` \| `suspended` \| `deleted`. |
| `metadata` | JSONB | Extensible profile attrs. |
| `created_at` / `updated_at` | TIMESTAMPTZ | |
| `deleted_at` | TIMESTAMPTZ NULL | Soft delete. |

### 2.2 `memories`
The semantic long-term store — the hot, queried row. **No embedding here** (see
`memory_embeddings`).

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `user_id` | UUID FK → users.id | Owner (indexed, RLS key). |
| `category` | TEXT (enum) | One of the 7 categories (§3). |
| `content` | TEXT | The distilled memory (not a transcript). |
| `summary` | TEXT NULL | Optional short form for context packing. |
| `importance_score` | REAL | 0.0–1.0 (§5). |
| `confidence_score` | REAL | 0.0–1.0 (§5). |
| `status` | TEXT (enum) | `active` \| `superseded` \| `archived`. |
| `supersedes_id` | UUID FK → memories.id NULL | Points to the memory this one replaces. |
| `source_type` | TEXT | `message` \| `document` \| `resume` \| `activity` \| `direct`. |
| `source_id` | UUID NULL | Polymorphic pointer to the originating row. |
| `consent_mode` | TEXT | How it was created (`explicit`/`assisted`/`autonomous`). |
| `is_sensitive` | BOOLEAN | Health/finance/credentials → Red path (default `false`). |
| `recall_count` | INTEGER | Times retrieved (reinforcement signal). |
| `last_recalled_at` | TIMESTAMPTZ NULL | Recency/decay input. |
| `content_tsv` | TSVECTOR (generated) | Full-text index source. |
| `metadata` | JSONB | Tags, entities, extracted slots. |
| `created_at` / `updated_at` | TIMESTAMPTZ | |
| `deleted_at` | TIMESTAMPTZ NULL | Soft delete (recoverable grace window). |

### 2.3 `memory_versions`
Immutable audit + edit history of each memory. Every content/score change or supersession
appends a row — never an in-place rewrite. Backs "inspect provenance" and undo.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `memory_id` | UUID FK → memories.id | Parent memory. |
| `user_id` | UUID FK → users.id | Denormalized for tenant queries + RLS. |
| `version_no` | INTEGER | Monotonic per memory (1,2,3…). |
| `content` | TEXT | Snapshot of content at this version. |
| `importance_score` | REAL | Snapshot. |
| `confidence_score` | REAL | Snapshot. |
| `change_reason` | TEXT (enum) | `created` \| `edited` \| `reinforced` \| `corrected` \| `superseded` \| `archived`. |
| `changed_by` | TEXT | `user` \| `system` \| `agent:<name>`. |
| `diff` | JSONB NULL | Structured delta vs. previous version. |
| `created_at` | TIMESTAMPTZ | Append-only; no updates/deletes. |

Constraint: `UNIQUE (memory_id, version_no)`.

### 2.4 `memory_embeddings`
Vectors, decoupled from the memory row so we can re-embed and run multiple models.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | |
| `memory_id` | UUID FK → memories.id | Parent (CASCADE on hard delete). |
| `user_id` | UUID FK → users.id | Tenant scope + RLS. |
| `embedding` | VECTOR(1536) | pgvector; dim matches `EMBEDDINGS_MODEL`. |
| `model` | TEXT | e.g. `text-embedding-3-small` (provenance for migrations). |
| `dim` | INTEGER | Vector dimensionality. |
| `content_hash` | TEXT | Hash of embedded text → skip re-embedding unchanged content. |
| `is_active` | BOOLEAN | Current vector for search; old models kept but inactive. |
| `created_at` | TIMESTAMPTZ | |

Constraint: `UNIQUE (memory_id, model)`; partial unique `(memory_id) WHERE is_active`.

### 2.5 Relationships

```
users (1) ──< (∞) memories (1) ──< (∞) memory_versions
                      │
                      └──< (∞) memory_embeddings   (1 active per memory)

memories.supersedes_id ──▶ memories.id            (self-referential history chain)
memories.(source_type, source_id) ─ ─▶ messages | documents | resume_versions
```

### 2.6 Indexes (the performance contract)

| Table | Index | Why |
| --- | --- | --- |
| `memories` | `(user_id)` btree | Tenant scoping on every query. |
| `memories` | `(user_id, category, status)` btree | Category-scoped active recall. |
| `memories` | `(user_id) WHERE deleted_at IS NULL` partial | Exclude soft-deleted cheaply. |
| `memories` | GIN on `content_tsv` | Full-text leg of hybrid search. |
| `memories` | GIN on `metadata` | Tag/entity filters. |
| `memories` | `(user_id, last_recalled_at)` btree | Recency ranking + decay sweeps. |
| `memory_embeddings` | **HNSW** on `embedding` (cosine) `WHERE is_active` | ANN vector search. |
| `memory_embeddings` | `(user_id)` btree | Tenant pre-filter before ANN. |
| `memory_versions` | `(memory_id, version_no)` unique | Ordered history. |
| all FKs | btree | Join performance + integrity. |

> **pgvector note:** HNSW (`m`, `ef_construction` tuned) gives strong recall/latency into
> the millions of vectors. Tenant filtering is applied so ANN scans stay user-scoped.

---

## 3. Memory Categories

Seven first-class categories (`memories.category`). Each drives category-scoped recall,
dashboard filtering, and which agent consumes it. **Sensitivity gates auto-save.**

| Category | Holds | Example | Primary source | Auto-save? | Consumed by |
| --- | --- | --- | --- | --- | --- |
| **Profile** | Identity: name, location, role, background | "Final-year ECE student in Bangalore" | onboarding, chat | Assisted+ | All agents |
| **Preference** | Working style, tone, communication prefs | "Prefers concise, bullet answers" | assisted/auto | Assisted+ | All agents / Personality |
| **Career** | Goals, target companies, skills, applications | "Targeting Qualcomm (embedded)" | command, resume | Assisted+ | Career Agent |
| **Learning** | Skills in progress, curricula, mastery | "Learning RTOS; 60% done" | Learning Agent | Assisted+ | Learning Agent |
| **Project** | Active builds, decisions, status | "Building GUMMY OS; Phase 1" | Builder Agent | Assisted+ | Builder Agent |
| **Conversation** | Distilled summaries of past chats | "Discussed RAG design Jun 4" | summarization worker | System | Orchestrator |
| **Document** | Knowledge extracted from files | "Resume v2: 2 internships, 5 projects" | ingestion | System | Career/Research |

**Sensitive sub-flag (`is_sensitive`)** — health, finance, credentials are **never**
auto-saved regardless of consent mode; they take the **Red permission** path
([security-system.md](../architecture/security-system.md)) and require explicit confirmation
before storage. Categorization is performed by `categorizer.py` (cheap Claude Haiku call +
deterministic rules), defaulting to the safest interpretation on ambiguity.

---

## 4. Memory Lifecycle

A small, auditable state machine. Every transition writes a `memory_versions` row and emits
a structured log/audit event.

```
            create                update                 archive
 (none) ───────────▶ active ───────────────▶ active ───────────▶ archived
                       │   │  (supersede)                          │
                       │   └────────────▶ superseded               │
                       │                                           │
              soft delete (deleted_at set, recoverable)            │
                       ▼                                           ▼
                   deleted ─────────── forget (hard purge) ─────▶ (gone)
```

| Transition | What happens | Consent / safety |
| --- | --- | --- |
| **Create** | `capture.py`: classify → score → **dedupe** → embed (async) → insert `memories` + v1 `memory_versions`. | Blocked if `memory_paused`; sensitive → explicit only. |
| **Update** | Reinforcement raises scores + `last_recalled_at`; edits append a version (never silent overwrite). Conflicts → **supersede**: old → `superseded`, new links via `supersedes_id`, history preserved. | User edits = `changed_by: user`; auto = `system`. |
| **Archive** | `status = archived` — excluded from default recall, retained + visible in Memory Center. Reversible. | Reversible; logged. |
| **Delete** | Soft delete: `deleted_at` set, hidden, recoverable for a grace window (e.g. 30 days). Deleting a source document offers cascade to derived memories. | Recoverable; cascade is opt-in. |
| **Forget** | Hard purge: permanently remove the `memories` row, **all** `memory_embeddings`, and versions (right to be forgotten). Irreversible. | Requires explicit confirmation; audit records the deletion event (not the content). |

---

## 5. Memory Scoring

Two independent 0.0–1.0 scores, set at creation and continuously adjusted. Both are **cheap
math + light heuristics** (a Haiku assist only where needed) so they cost almost nothing.

### 5.1 `confidence_score` — *how sure are we it's true?*

| Signal | Effect |
| --- | --- |
| Direct user statement ("remember that…") | High: **0.9–1.0** |
| Strong contextual evidence (stated in passing, consistent) | Medium-high: **0.7–0.9** |
| Inferred from behavior/pattern | Medium: **0.5–0.7** |
| Weak/ambiguous signal | Low: **< 0.5** → never auto-saved |
| **Reinforcement** (same fact re-encountered) | `+Δ` toward 1.0 (diminishing) |
| **Contradiction** | `−Δ`; if a newer fact wins, old is superseded |

### 5.2 `importance_score` — *how much does it matter to serving the user?*

| Signal | Effect |
| --- | --- |
| Identity, active goals, current projects | High: **0.8–1.0** |
| Stable preferences | Medium-high: **0.6–0.8** |
| Situational/context | Medium: **0.4–0.6** |
| Trivia / one-off | Low: **< 0.4** |
| **Recall reinforcement** (`recall_count`↑) | small boost — used memories matter |
| **Time decay** | `importance *= exp(-λ · days_since_last_recall)` unless reinforced |

**Update triggers:** on create (initial assignment by `source_type` + category), on recall
(reinforce the memories actually used), on edit/correction, and on a periodic **decay sweep**
(worker) that gently lowers stale, never-recalled memories so noise fades.

> Scores are **storage/lifecycle** signals. They also feed retrieval ranking (§6) but are not
> the same as the per-query relevance score — a high-importance memory irrelevant to the
> current query still ranks low because semantic similarity dominates.

---

## 6. Memory Retrieval Pipeline

The read path, run on every turn that needs context. Target: **p95 < 150 ms** for retrieval
(excluding the Claude call). Exposed via `memory_service.recall()` so every future agent
recalls identically.

```
User Query
   │
   ▼
1. Pre-process ──── normalize text; pull active conversation; detect intent + likely
   │                categories (Career? Profile?) via cheap rules/Haiku.
   ▼
2. Embedding Search ── embed the query (same model as stored); ANN search over
   │                   memory_embeddings (HNSW, cosine) WHERE user_id = me AND is_active,
   │                   pre-filtered by tenant + (status=active, not deleted, category ∈ set).
   │                   In parallel: Postgres full-text match on content_tsv for exact terms.
   ▼
3. Ranking ──────── merge vector + full-text candidates; compute combined relevance:
   │                   score = w1·semantic_similarity
   │                         + w2·importance_score
   │                         + w3·recency            (decayed last_recalled_at/created_at)
   │                         + w4·confidence_score
   │                         + w5·category_match
   │                   weights live in core/constants.py (tunable, A/B-able).
   ▼
4. Memory Selection ─ MMR (maximal marginal relevance) to drop near-duplicates and add
   │                   diversity; take top-K candidates above a relevance floor.
   ▼
5. Context Assembly ─ context_assembler.py packs within a token budget: group by category,
   │                   prefer `summary` over full `content` when long, include provenance
   │                   tags; oldest/low-value trimmed first. Returns a structured pack
   │                   (+ which memory_ids were used).
   ▼
6. Claude ────────── pack injected into the prompt via llm_gateway (system prompt + memory
                     pack are prompt-cached); response streamed. Post-call: reinforce used
                     memories (recall_count++, last_recalled_at=now, importance bump) and
                     trace the recall in Langfuse (which memories, scores, tokens, cost).
```

**Resilience:** if the embedding provider is down, fall back to full-text + importance/recency
ranking so recall degrades gracefully rather than failing. Hot query embeddings and the
assembled pack are cacheable (Redis) per conversation turn.

---

## 7. Resume Version System

The resume is a first-class, **versioned** artifact (critical for the Phase 2 Career Agent).
Built on two tables layered over documents.

### 7.1 Tables

`resumes` (one logical resume per user, the pointer):
`id`, `user_id`, `active_version_id` (FK → resume_versions.id NULL), `title`,
`created_at`, `updated_at`.

`resume_versions` (immutable snapshots — V1, V2, V3…):
`id`, `resume_id` FK, `user_id`, `version_no`, `document_id` FK → documents.id,
`parsed_json` JSONB (structured: contact, summary, experience[], education[], skills[],
projects[]), `raw_text` TEXT, `source` (`upload`/`tailored`), `base_version_id` (NULL for
uploads; set for job-tailored variants), `created_at`. Uploading never overwrites — it
appends a new version and moves `active_version_id`.

### 7.2 Upload → diff → memory-sync workflow

```
Upload resume.pdf
   ▼
ingestion: parse → structure into parsed_json → create resume_version (V_n, active)
   ▼
diff V_n vs V_(n-1): structured comparison of experience/skills/education/projects
   ▼
sync Career Memory: add new facts (e.g. "+ Qualcomm internship 2025"),
                    supersede outdated ones (old objective line → superseded)
   ▼
notify user: "Got resume v2 — new Qualcomm internship added; retire the old objective?"
```

### 7.3 Comparison workflow (V1 ↔ V2 ↔ V3)

`resume_service.compare(version_a, version_b)` returns a structured diff:

| Diff facet | Output |
| --- | --- |
| **Experience** | added / removed / changed roles (title, company, dates, bullets). |
| **Skills** | skills added vs. dropped (set delta). |
| **Education / Projects** | added / removed / edited entries. |
| **Summary/Objective** | text diff with change highlights. |
| **Memory impact** | which Career memories would be created/superseded by adopting B. |

Any two versions are comparable (not just consecutive), powering the Memory Center version
history UI and "what changed since V1?" Tailored, job-specific variants reference a
`base_version_id` so the lineage stays clear.

---

## 8. API Endpoints (Phase 1)

All under `/api/v1`, JWT-authenticated (Supabase), **tenant-scoped by `user_id` + RLS**.
JSON unless noted; cursor pagination on lists.

**Identity & settings**
| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/me` | Current user profile + consent state. |
| `PATCH` | `/settings/consent` | Set consent mode (`explicit`/`assisted`/`autonomous`). |
| `POST` | `/settings/memory/pause` | Toggle the global pause-memory switch. |

**Memories (capture + lifecycle)**
| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/memories` | Create a memory (direct/explicit). Runs score+dedupe. |
| `GET` | `/memories` | List/filter by `category`, `status`, search. |
| `GET` | `/memories/{id}` | Fetch one (with provenance). |
| `PATCH` | `/memories/{id}` | Edit content → appends a version. |
| `POST` | `/memories/{id}/archive` | Archive (reversible). |
| `POST` | `/memories/{id}/supersede` | Supersede with a new memory (links history). |
| `DELETE` | `/memories/{id}` | Soft delete (recoverable). |
| `POST` | `/memories/{id}/forget` | Hard purge (row + embeddings + versions). |
| `GET` | `/memories/{id}/versions` | Full version/supersession history. |

**Retrieval (the read path)**
| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/memories/recall` | Hybrid search → ranked memories for a query (agent-facing). |
| `POST` | `/context/assemble` | Token-budgeted context pack for a query (debug/inspection). |
| `GET` | `/memories/summary` | "What do you know about me?" — grouped by category. |

**Documents**
| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/documents` | Upload (→ Supabase Storage); enqueue ingestion. |
| `GET` | `/documents` | List documents. |
| `GET` | `/documents/{id}` | Document + ingestion status + derived memories. |
| `DELETE` | `/documents/{id}` | Delete (offer cascade to derived memories). |

**Resumes**
| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/resumes/upload` | Upload → new version (active). |
| `GET` | `/resumes` | The resume + its versions. |
| `GET` | `/resumes/versions/{id}` | One version (structured + raw). |
| `POST` | `/resumes/active` | Set the active version. |
| `GET` | `/resumes/compare?a={id}&b={id}` | Structured diff between two versions. |

**Conversations & messages (memory-capture source)**
| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/conversations` | Start a thread. |
| `GET` | `/conversations` | List threads. |
| `POST` | `/conversations/{id}/messages` | Append a message (triggers capture pipeline). |
| `GET` | `/conversations/{id}/messages` | Ordered messages. |

**Ops**
| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` / `/health/ready` | Liveness / readiness (DB + pgvector + LLM). |

---

## 9. Week 1 Build Plan

Week 1 ships a **working vertical slice of the memory engine**: create a memory, embed it,
recall it via hybrid search, and read it back over the API — CI green throughout. Document
ingestion polish and resume diff complete in Week 2 (see Exit Criteria for full-Phase scope).

| Day | Goal | Checklist |
| --- | --- | --- |
| **Day 1 — Scaffold** | Backend boots; CI activates. | ☐ `backend/` per §1 ☐ `pyproject.toml` (uv, Ruff/Black/mypy/pytest) ☐ `config.py` reads `.env` ☐ FastAPI app + `/health` ☐ Dockerfile ☐ CI backend job green |
| **Day 2 — Data layer** | Schema live with RLS. | ☐ ORM models (users, memories, memory_versions, memory_embeddings) ☐ Alembic migration ☐ enable `pgvector` + HNSW index ☐ RLS policies + tenant GUC ☐ async session/pooling ☐ migration runs on Supabase |
| **Day 3 — Embeddings + LLM seam** | Text → vector; Claude reachable. | ☐ `embedding_service` (provider-abstracted, batch, content-hash cache) ☐ `llm_gateway` (tiered models, retries, prompt caching) ☐ unit tests with a fake embedder/LLM |
| **Day 4 — Capture + scoring** | Memories are born correctly. | ☐ `categorizer` (7 categories + sensitive flag) ☐ `scoring` (importance+confidence heuristics) ☐ `capture` (dedupe + supersede + v1 version) ☐ consent/pause checks ☐ unit tests on scoring/dedupe |
| **Day 5 — Retrieval pipeline** | Recall works end to end. | ☐ `memory_repo` hybrid SQL (vector + filter + full-text) ☐ `retrieval` weighted ranking + MMR ☐ `context_assembler` token budget ☐ reinforcement on recall ☐ integration test: store→recall returns the right memory |
| **Day 6 — API surface** | Endpoints live + secured. | ☐ memories CRUD + lifecycle routes ☐ `/recall`, `/context/assemble`, `/memories/summary` ☐ conversations/messages ☐ JWT auth dep + tenant scoping ☐ Pydantic schemas ☐ endpoint tests |
| **Day 7 — Harden + prove** | Trustworthy slice. | ☐ Langfuse tracing on recall ☐ structured logs + error handlers ☐ seed script + demo run of memory-system Workflows A & B ☐ Ruff/Black/mypy/pytest all green in CI ☐ short `backend/README.md` |

---

## 10. Phase 1 Exit Criteria

Phase 1 is **done** when all hold (per [CONVENTIONS.md §9](../../CONVENTIONS.md) Definition of
Done — implemented, tested, documented, secure, reviewed):

**Functional**
- ☐ Schema (`users`, `memories`, `memory_versions`, `memory_embeddings`, `documents` +
  `document_chunks`, `resumes` + `resume_versions`) migrated with **RLS** + indexes.
- ☐ **Capture** pipeline: consent-aware, scored, deduped, supersession-preserving, with
  sensitive categories on the Red path.
- ☐ **Embedding** generation (async) and re-embedding by content-hash.
- ☐ **Hybrid retrieval** returns a ranked, token-budgeted context pack within latency
  target (p95 < 150 ms retrieval), with graceful degradation if embeddings are down.
- ☐ **Lifecycle**: create/update/archive/soft-delete/forget all work and are versioned.
- ☐ **Document ingestion**: upload → parse → chunk → embed → index → derive memories →
  recallable.
- ☐ **Resume versioning**: versioned uploads, active pointer, structured diff, Career-memory
  sync.
- ☐ All §8 endpoints implemented, authenticated, and tenant-scoped.

**Quality & safety**
- ☐ Meaningful tests on the risky core: **scoring, ranking, dedupe, supersession, diff,
  permission/consent** — CI green (Ruff/Black/mypy/pytest).
- ☐ Observability: Langfuse traces on recall (which memories, scores, tokens, cost) +
  structured logs; per-user usage sane.
- ☐ No secrets committed; every data path `user_id`-scoped; RLS verified by test.

**Acceptance — the memory-system workflows pass end to end**
- ☐ **A:** "I'm preparing for Qualcomm… remember that" → Career memory created (high
  importance/confidence, explicit consent).
- ☐ **B:** "What do you know about me?" → grouped recall across categories, nothing
  fabricated, all editable.
- ☐ **C:** new resume upload → V2 created, diffed, Career memory updated, outdated line
  flagged.
- ☐ **D:** "Actually I'm targeting NVIDIA now" → Qualcomm memory superseded, NVIDIA linked
  via `supersedes_id`, history retained.

**Definition of Phase-1 done:** a new conversation message can silently become durable,
consented, scored memory; that memory is recalled and shapes Gummy's next answer; and the
user can see, edit, version, and forget all of it in the Memory Center backend — *without a
single specialized agent existing yet.* The moat is in place; Phase 2 (Career Agent) builds
on it.

---

_Related: [memory-system.md](../architecture/memory-system.md),
[database-design.md](../architecture/database-design.md),
[system-design.md](../architecture/system-design.md),
[adrs/ADR-002-memory-first.md](../architecture/adrs/ADR-002-memory-first.md),
[adrs/ADR-003-postgresql-pgvector.md](../architecture/adrs/ADR-003-postgresql-pgvector.md)._
