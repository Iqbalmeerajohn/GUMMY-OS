# GUMMY OS

> A Personal, Memory-First **Multi-Agent AI Operating System**. Your assistant's
> name is **Gummy**.

GUMMY OS is a unified, agentic operating layer that manages personal life, career,
learning, research, and planning through a coordinated team of specialized AI
agents — all backed by a persistent, **consent-based long-term memory** behind
**fail-closed multi-tenant isolation**.

**Gummy** learns you through conversation, memory, documents, and goals — while
staying secure, permission-based, and user-controlled. It is built **first for
personal use**, with a deliberate path toward a multi-user **SaaS** platform.

---

## Status — M8.5 development freeze (2026-06-24)

Active development is **paused** at the M8.5 freeze point. The substrate is built,
tested, and documented; the project resumes at **M9 (Workflow Learning)**.

| Area | State |
| --- | --- |
| Phases complete | 0, 1, 1.5, 2, 3 ✅ · Phase 4 partial (M7, M8, M8.5) 🟡 |
| Backend tests | **598 passing**, 0 failing (4 Postgres-gated skips) |
| Migrations | 21 Alembic revisions |
| API | ~55 REST endpoints across 10 routers (`/api/v1`) |
| Agents | 5 specialists + general + recall (deterministic router) |
| Stack | Python 3.12 · FastAPI · SQLAlchemy 2.0 async · PostgreSQL/pgvector · Next.js 16 / React 19 |

**What works today:** memory engine, JWT auth + fail-closed RLS, conversation
engine (streaming, summaries, chat→memory extraction), goals, file intelligence
(keyword RAG + attachments), unified knowledge layer, and a routed five-specialist
agent workforce — with Langfuse / Sentry / PostHog observability.

**Seam-only (not yet wired):** live web search (Brave/Tavily), vector file RAG,
and the action/automation layer (scaffolded via the Green/Yellow/Red approval model).

---

## Repository structure

```
GUMMY-OS/
├── README.md, CONVENTIONS.md, .env.example
├── architecture/            # Design specs + ADRs
├── docs/                    # Product docs, release notes, freeze document set
├── backend/                 # FastAPI app, agent runtime, services, tests
│   └── app/{api,core,database,models,repositories,schemas,services,workers}
└── frontend/                # Next.js 16 / React 19 web client
```

---

## Documentation map

**Freeze document set (start here):**
1. [Master Document](docs/GUMMY_OS_MASTER_DOCUMENT.md) — the single canonical record
2. [Project Audit](docs/PROJECT_AUDIT.md) — code-verified inventory & technical debt
3. [The GUMMY OS Story](docs/GUMMY_OS_STORY.md) — product history
4. [Technical Architecture](docs/GUMMY_OS_ARCHITECTURE.md) — all layers, as-built
5. [Product Overview](docs/PRODUCT_OVERVIEW.md) — what it is for users
6. [Test Report](docs/TEST_REPORT.md) — verification snapshot
7. [Résumé & Interview Positioning](docs/RESUME_PROJECT_SUMMARY.md)
8. [Future Roadmap](docs/FUTURE_ROADMAP.md) — Phase 4 remaining → Phase 9

**Design specs:** [VISION.md](docs/VISION.md) · [ROADMAP.md](docs/ROADMAP.md) ·
[FEATURES.md](docs/FEATURES.md) · [architecture/](architecture/) ·
[CONVENTIONS.md](CONVENTIONS.md)

**Release notes:** [M4](docs/06_RELEASE_NOTES_M4.md) ·
[M6](docs/07_RELEASE_NOTES_M6.md) · [M6.5](docs/08_RELEASE_NOTES_M6_5.md) ·
[M8](docs/09_RELEASE_NOTES_M8.md)

---

## Running the backend

```bash
cd backend
uv sync                       # or: pip install -r requirements.txt
# configure .env from .env.example
.venv/Scripts/python -m pytest -q     # 598 passed, 4 skipped
uvicorn app.main:app --reload          # OpenAPI at /docs
```

The Postgres-gated security suite (fail-closed RLS, cross-tenant rejection) runs
with `RUN_RLS_PG_TESTS=1` and `RLS_TEST_DSN` pointed at a `gummy_app` DSN.

## Running the frontend

```bash
cd frontend
npm install
npm run dev        # Next.js dev server
```

---

_Maintained as a single-founder project with the discipline of a startup
engineering org._
