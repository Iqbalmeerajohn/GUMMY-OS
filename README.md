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

## Status — M9 Local-First (2026-08-12)

GUMMY runs **entirely on your machine**. No Supabase, no Railway, no Vercel, no
Sentry, no PostHog — those SDKs are gone from both dependency manifests, there is
one JWT issuer (this server), and errors and product events are logged locally.
One Postgres container, one Ollama daemon, two dev servers. Paid model keys
(OpenAI / Claude) still work; they are simply optional.

| Area | State |
| --- | --- |
| Backend tests | **655 passing**, 0 failing (4 Postgres-gated skips) |
| Migrations | 23 Alembic revisions |
| API | ~60 REST endpoints across 11 routers (`/api/v1`) |
| Agents | 5 routed specialists + general + recall; the rest are in the plan phase |
| Web client | 6 routes — the chat *is* the app, everything else is a slide-over |
| Stack | Python 3.12 · FastAPI · SQLAlchemy 2.0 async · PostgreSQL 16 + pgvector · Ollama · Next.js 16 / React 19 |

**What works today:** local auth (email/password + Google OAuth + owner mode)
with fail-closed RLS · the memory engine with consolidation, a learned user
profile, an episodic timeline, and reinforcement/decay ranking · instant recall
(~0.6 s end-to-end, no model call, vs ~3 s generated) · streaming conversations with summaries and
chat→memory extraction · goals · file intelligence · unified knowledge · the
routed agent workforce · calendar import.

**Seam-only (not yet wired):** Gmail/Drive connectors, live web search
(Brave/Tavily), vector file RAG, and the action/automation layer.

See [M9 release notes](docs/10_RELEASE_NOTES_M9_LOCAL_FIRST.md) for the full
account of what changed and what comes next.

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

**Current (start here):**
1. [M9 — Local-First GUMMY](docs/10_RELEASE_NOTES_M9_LOCAL_FIRST.md) — what the
   system is today, and what is next

**Freeze document set (M8.5 history — these still describe the hosted stack):**
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
[M8](docs/09_RELEASE_NOTES_M8.md) ·
[M9](docs/10_RELEASE_NOTES_M9_LOCAL_FIRST.md)

---

## Running it locally

Everything below runs on one machine. Nothing needs an account anywhere.

**1. Database** — Postgres 16 + pgvector + pg_trgm, in Docker:

```bash
docker compose up -d db        # container `gummy-db` on :5432
```

**2. Models** — [Ollama](https://ollama.com) provides both chat and embeddings,
free and offline:

```bash
ollama pull qwen2.5:3b         # chat
ollama pull nomic-embed-text   # embeddings (768-d)
```

**3. Backend:**

```bash
cd backend
uv sync                                  # or: pip install -r requirements.txt
cp .env.example .env                     # defaults are already local-first
.venv/Scripts/alembic upgrade head       # 23 revisions
.venv/Scripts/python -m pytest -q        # 655 passed, 4 skipped
.venv/Scripts/uvicorn app.main:app --reload   # OpenAPI at /docs
```

**4. Frontend:**

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
```

Sign up with an email and password, or set `GUMMY_OWNER_MODE=true` to skip the
login screen entirely on a single-user machine.

**Optional — Google sign-in.** Create an OAuth client (Web application) in the
Google Cloud console with redirect URI
`http://localhost:8000/api/v1/auth/google/callback`, then set `GOOGLE_CLIENT_ID`
and `GOOGLE_CLIENT_SECRET` in `backend/.env`. The button appears by itself once
the server reports the method as available.

**Optional — paid models.** Set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` and
switch `LLM_PROVIDER`. Ollama remains the default so the product costs nothing to
run.

The Postgres-gated security suite (fail-closed RLS, cross-tenant rejection) runs
with `RUN_RLS_PG_TESTS=1` and `RLS_TEST_DSN` pointed at a `gummy_app` DSN.

---

_Maintained as a single-founder project with the discipline of a startup
engineering org._
