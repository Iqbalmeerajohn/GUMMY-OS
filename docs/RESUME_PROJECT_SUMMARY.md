# GUMMY OS — Résumé & Interview Positioning

> Career-facing summary of GUMMY OS at the M8.5 freeze point, tuned for resume
> bullets, LinkedIn, and technical interviews. All metrics are code-verified
> (`PROJECT_AUDIT.md`, `TEST_REPORT.md`).

---

## 1. The one-liner (project headline)

**GUMMY OS** — *Designed and built a multi-tenant, memory-first AI operating
system: a FastAPI + PostgreSQL/pgvector backend with fail-closed Row-Level
Security, a unified semantic-retrieval knowledge layer, and a routed multi-agent
workforce — verified by ~600 automated tests across 9 delivery milestones.*

---

## 2. Verified facts to quote

| Fact | Value |
| --- | --- |
| Automated backend tests | **598 passing**, 0 failing (4 Postgres-gated skips) |
| Delivery milestones | **9** (M0→M8.5) across 5 completed phases |
| Database migrations | 21 Alembic revisions |
| REST endpoints | ~55 across 10 routers |
| Specialized agents | 5 specialists + general + recall (7 manifests) |
| Stack | Python 3.12, FastAPI, SQLAlchemy 2.0 async, PostgreSQL/pgvector, Next.js 16/React 19 |
| Security | Fail-closed Postgres RLS under a non-bypass role, proven live |

---

## 3. Résumé bullets (pick 3–4)

**Backend / platform focus**
- Architected and built a **multi-tenant AI backend** (FastAPI, PostgreSQL/pgvector,
  SQLAlchemy 2.0 async) with **fail-closed Postgres Row-Level Security** enforcing
  per-user isolation at the database layer, verified live by a Postgres-gated test
  suite running as a non-bypass role.
- Engineered a **memory-first retrieval system** — hybrid semantic + keyword search
  (pgvector HNSW + Postgres full-text) ranked by importance/recency/confidence —
  powering memory-grounded, token-budgeted LLM responses.
- Built a **unified knowledge-retrieval layer** that ranks and compresses memories,
  conversation summaries, goals, and documents into a single grounded context pack,
  enforcing a "single retrieval layer" rule so new agents add zero retrieval code.

**AI / agent focus**
- Designed a **multi-agent orchestration runtime** with a deterministic keyword
  router, single/pipeline/parallel execution shapes, per-run step & token-cost
  guards, and a guaranteed fallback so routing never fails a request — with a full
  agent-to-agent audit trail and Langfuse tracing.
- Shipped **five specialized agents** (career, learning, planner, memory, research)
  on a shared handler that grounds exclusively through the knowledge seam, plus a
  read-only routing-diagnostics API.

**Delivery / quality focus**
- Delivered across **9 incremental milestones** with **598 automated tests** (0
  failing), `ruff`/`mypy`-clean, 21 Alembic migrations, and live verification on
  Supabase Postgres — as a disciplined single-founder engineering effort.

**Full-stack focus**
- Built the **Next.js 16 / React 19** web client: streaming (SSE) chat workspace
  with agent selection, a Memory Center, goals, file upload + chat attachments, and
  unified search — with TanStack Query, Supabase SSR auth, and PostHog/Sentry.

---

## 4. LinkedIn "About / Featured" blurb

> *Building **GUMMY OS** — a personal, memory-first AI operating system. A
> FastAPI + PostgreSQL/pgvector backend with fail-closed Row-Level Security, a
> consent-based long-term memory engine, a unified semantic-retrieval knowledge
> layer, and a routed multi-agent workforce (career, learning, planner, memory,
> research). ~600 automated tests, 21 migrations, a streaming Next.js/React client.
> Solo-built with startup engineering discipline.*

---

## 5. Interview talking points (Q → A)

**"How do you guarantee one user can't read another's data?"**
Postgres Row-Level Security keyed on a per-transaction GUC set from the verified
JWT, enforced under a dedicated `NOSUPERUSER/NOBYPASSRLS` role so policies actually
apply, **fail-closed** (unset tenant → zero rows), with `WITH CHECK` on writes.
Proven by a live cross-tenant test suite — including under full-text and vector
search. The hard-won lesson: I make each migration ship the table's *full* access
policy (RLS **and** grants) so security travels with the schema and can't drift.

**"How do you keep an AI assistant cheap and coherent over long histories?"**
Rolling conversation summaries (versioned + embedded) plus token-budgeted context
assembly — the model never replays the full thread. Long histories stay bounded in
latency and token cost.

**"How does chat become long-term memory safely?"**
Consent-gated extraction routed through the existing memory engine (no duplicated
scoring/versioning/embedding logic), provenance-linked, and **watermark-first** —
so an LLM failure rolls back and retries, and a success never re-extracts (no
duplicates). It runs on an async worker off the request path.

**"How does routing to multiple agents stay reliable?"**
The router is deterministic and free (weighted keyword scoring) so the same intent
always routes the same way and a diagnostics endpoint can explain it. Below
threshold it degrades to a general agent; the orchestrator wraps every run with a
guaranteed fallback to the grounded single-agent reply; per-run step and token
caps stop runaway plans. Routing never costs the user a reply.

**"Why a 'single retrieval layer'?"**
So retrieval logic, cost, and tenant-scoping live in exactly one place. Five
specialists shipped without five retrieval implementations — they all ground
through one ranked, compressed knowledge seam.

**"How would this scale to many users?"**
Stateless services over a stateful store (any instance serves any request),
denormalized tenant columns for cheap index-friendly RLS on hot tables, ANN +
GIN indexing, and an in-process worker contract that maps directly onto a shared
queue (Redis/Celery) when multi-process scale-out is needed.

**"What's your testing philosophy?"**
A hermetic SQLite suite for speed (zero infra, ~32s) where Postgres-only features
degrade gracefully, plus a Postgres-gated suite that proves the security-critical
guarantees against real Postgres. LLM/embeddings run behind deterministic fakes —
no network, no flakiness, no spend.

---

## 6. Competencies this project demonstrates

- **System design:** layered architecture, acyclic module graph, provider
  abstractions, designed-for-scale multi-tenancy.
- **Data/database:** PostgreSQL, pgvector (HNSW), full-text search, RLS, migrations.
- **AI engineering:** retrieval-augmented grounding, agent orchestration, prompt
  architecture, LLM provider abstraction, cost/observability.
- **Security:** database-enforced isolation, JWT auth, consent & provenance,
  defense-in-depth, live security verification.
- **Quality:** 598-test suite, lint/type gates, incremental milestone delivery,
  honest scoping (seams vs. shipped features).
- **Full-stack:** Next.js/React streaming UI, server-state caching, SSR auth.
- **Product/ownership:** vision → roadmap → shipped increments, solo, with docs.

---

## 7. Honesty guardrails (so you never overclaim in an interview)

- Live **web search is a seam**, not a wired feature (Brave/Tavily pending; off by
  default). Say "I built the provider abstraction and eligibility gating."
- File RAG is **keyword retrieval**, not vector ranking yet. Say "keyword RAG with
  a seam for a vector retriever."
- The **action layer is scaffolded** (approval/permission model exists); Gummy
  proposes actions but doesn't execute external ones yet.
- Workers are **in-process** (asyncio), not a distributed queue — by design, with a
  clear externalization path.

Framing these as *deliberate seams with a designed path forward* is itself a
strong signal of engineering judgment.
