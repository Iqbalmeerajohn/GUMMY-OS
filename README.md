# GUMMY OS

> A local-first personal AI operating system: persistent memory, multi-agent
> orchestration, safe tool execution, and durable automation — running entirely
> on your own machine.

Your assistant is called **Gummy**. It learns useful things from your
conversations, keeps them in a local PostgreSQL database, and uses them quietly
— only when they bear on what you just asked.

**No Supabase. No Railway. No Vercel backend. No paid infrastructure.** One
Postgres container, one Ollama daemon, two dev servers.

---

## Status

| Area | State |
| --- | --- |
| Backend tests | **915 passed**, 4 skipped (Postgres-gated), 0 failed |
| Frontend tests | **18 passed**, 0 failed |
| TypeScript · ESLint | clean |
| `ruff` · `black` · `mypy app` | clean (240 source files) |
| `mypy tests` | 57 pre-existing errors — [reported, not hidden](docs/VERIFICATION_REPORT.md#1-automated-checks) |
| Migrations | 25 Alembic revisions |
| API | 73 endpoints across 15 routers |
| Agents | 6 routed specialists + general + recall |
| Tools | 9 executable, 2 modeled behind approval |

Every number above was produced by running the thing. See the
[Verification Report](docs/VERIFICATION_REPORT.md) for exact denominators.

---

## Architecture

```mermaid
flowchart TD
    U[User] --> FE[Next.js 16 · localhost:3000]
    FE -->|Bearer JWT · SSE| API[FastAPI · localhost:8000]
    API --> ORCH[Master Orchestrator]

    ORCH --> ROUTER[Deterministic Router]
    ROUTER --> AGENTS

    subgraph AGENTS [Agents]
        CAREER[Career]
        LEARN[Learning]
        RESEARCH[Research]
        AUTO[Automation]
        GEN[General · Planner · Memory · Recall]
    end

    AGENTS --> KNOW[Unified Knowledge<br/>memories + goals + files]
    AGENTS --> LOOP[Tool Loop<br/>registry → policy → executor]

    LOOP --> TOOLS
    subgraph TOOLS [Tools]
        T1[calculator]
        T2[memory_read]
        T3[file_search / file_list]
        T4[web_search]
        T5[current_time]
        T6[automation_create / list]
    end

    KNOW --> DB[(PostgreSQL 16 + pgvector)]
    LOOP --> DB
    ORCH --> DB
    AGENTS --> OLLAMA[Ollama<br/>qwen2.5:3b · nomic-embed-text]
    SCHED[Automation Scheduler] --> DB
```

Every agent shares **one** memory engine, **one** knowledge seam, **one** tool
loop, and **one** orchestrator. Agent identity lives entirely in prompts.

---

## What works

### Memory
Facts are extracted from conversation automatically, consolidated against what
is already known (restatements reinforce; more specific versions supersede), and
retrieved by hybrid ranking — semantic similarity blended with importance,
confidence, and recency.

**Memory stays silent unless relevant.** A measured **0.45 semantic floor**
(calibrated against the real embedding model, not guessed) keeps unrelated
memories out of the prompt entirely, and the prompt tells the model to use
context without announcing it. Ask *"what is the capital of France?"* and zero
memories are injected.

**Instant recall** answers direct questions about stored facts with no model
call at all — sub-second, versus ~3 s generated.

### Agents
Career · Learning · Research · Automation, plus Planner, Memory, General, and a
deterministic Recall agent. Routing is keyword-based, free, and needs no LLM.

**Compound requests become pipelines.** *"Find AI jobs and then create a
learning plan for the biggest gap"* runs Career → Learning, with structured
findings handed between them. Detection is grammatical, so *"find jobs and
internships"* correctly stays one agent.

### Tools
A registry → policy → executor path with Green/Yellow/Red tiers, JSON-Schema
validation, per-tool timeouts, a 4-iteration loop cap, and redacted audit rows.
The calculator parses with an AST allowlist — `eval` is never used, so
`__import__('os').system(...)` is rejected at parse level.

### Automation
Reminders and recurring check-ins persisted in PostgreSQL, **surviving a
restart** — verified by restarting the backend and re-querying. Duplicate
execution is prevented by a unique constraint, not by careful sequencing.

They run inside GUMMY and **do not send email or create calendar events.**

### Authentication
GUMMY is its own identity provider: HS256 JWTs, PBKDF2 at 600k iterations,
rotating hashed refresh tokens, and Row-Level Security on all 25 tenant tables.
Verified live: **26/26** checks including two-user isolation.

**Password recovery works offline.** Reset tokens are stored only as a SHA-256
hash, are single-use, expire in 45 minutes, and revoke every session on the
account when redeemed. `forgot-password` returns a byte-identical response for
known and unknown addresses, so it cannot be used to discover who has an
account. With no email provider configured the reset link is written to the
backend log tagged `[GUMMY AUTH]` — the whole flow is testable locally, and
nothing ever claims an email was sent when none was. Verified live: **19/19**,
plus the full browser round trip.

---

## Running locally

**Local development only.** There is no public deployment — GUMMY runs on your
machine by design, because the point of the product is that your memory never
leaves it. The URLs below are not reachable by anyone else.

### Prerequisites
Docker · Python 3.12 · Node 22 · [Ollama](https://ollama.com)

```bash
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
```

### Start

```bash
docker compose up -d
```

```bash
cd backend && cp .env.example .env && uv sync && uv run alembic upgrade head && uv run uvicorn app.main:app --reload
```

```bash
cd frontend && npm install && npm run dev
```

| | URL |
| --- | --- |
| App (local) | **http://localhost:3000** |
| API (local) | **http://localhost:8000** |
| Swagger | **http://localhost:8000/docs** |
| Health | **http://localhost:8000/health** |

### Environment

Everything required is local. All external providers are optional.

| Variable | Purpose | Required |
| --- | --- | --- |
| `DATABASE_URL` | App connection (`gummy_app`, RLS-enforced) | yes |
| `DIRECT_DATABASE_URL` | Migrations + auth (owner role) | yes |
| `GUMMY_JWT_SECRET` | Token signing | yes |
| `LLM_PROVIDER` / `OLLAMA_MODEL` | Defaults to local Ollama | — |
| `EMBEDDINGS_PROVIDER` | Defaults to `nomic-embed-text` (768-d) | — |
| `GUMMY_OWNER_MODE` | Skips the login screen — **also disables sign-out** | leave `false` |
| `GOOGLE_CLIENT_ID` / `_SECRET` | Enables the Google button | optional |
| `AUTH_EMAIL_MODE` | `console` (log the reset link) or `smtp` | — |
| `SMTP_*` | Real email delivery, only when mode is `smtp` | optional |
| `BRAVE_API_KEY` | Enables live web search | optional |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Alternative model providers | optional |

Never commit `.env`. `.env.example` carries empty placeholders only.

---

## Documentation

| Document | Contents |
| --- | --- |
| [Verification Report](docs/VERIFICATION_REPORT.md) | Every metric, with commands and denominators |
| [Authentication](docs/AUTHENTICATION.md) | Sessions, sign-out, Google OAuth, isolation |
| [Agent Workforce](docs/AGENT_WORKFORCE.md) | The four agents and durable automation |
| [Multi-Agent Delegation](docs/MULTI_AGENT_DELEGATION.md) | Compound routing and hand-offs |
| [Tool System](docs/TOOL_SYSTEM.md) | Registry, policy, executor, the loop |
| [Architecture](docs/GUMMY_OS_ARCHITECTURE.md) | Layer-by-layer (M8.5 history) |
| [Résumé Summary](docs/RESUME_PROJECT_SUMMARY.md) | Positioning and talking points |
| [Roadmap](docs/FUTURE_ROADMAP.md) | What comes next |

Documents numbered `01`–`10` are release notes and describe the state at the
time they were written.

---

## Limitations

Stated plainly, because a README that hides these is not useful.

- **Google sign-in is implemented but unverified** — no credentials on this
  machine, so the round trip has never been tested. The button hides itself
  until the backend reports credentials.
- **Parallel agent routing is not implemented.** The executor exists and is
  tested; no keyword pattern produces a parallel plan.
- **File retrieval is keyword-based.** There is no vector RAG over file chunks.
- **Live web search is config-gated.** Without a key, agents say so rather than
  fabricating results.
- **Auth email is console-mode locally.** SMTP is implemented and unit-tested,
  but no real send has been performed from this machine.
- **No rate limiting** on login or forgot-password — local-only concerns today.
- **Automations run only while GUMMY is running**, and there is no notification
  channel — a fired reminder appears in the Automations panel.
- **No connectors.** Gmail, Calendar, GitHub, Slack are not implemented; only
  `.ics` calendar import exists.
- **No public deployment**, and no cloud infrastructure.
- **Tokens live in localStorage**, a deliberate trade for the `:3000`→`:8000`
  split.

---

## Roadmap

1. **Parallel agent routing** — the executor is built; detection is not.
2. **Vector file RAG** — `file_chunk_embeddings` mirroring the proven
   `memory_embeddings` HNSW pattern.
3. **Model gateway tiering** — per-call provider selection; `qwen3:8b` is
   already on disk as the local complex tier.
4. **Connector credentials** — an encrypted token store, unblocking Gmail and
   Drive.
5. **LangGraph**, evaluated only once the tool loop and delegation are proven.

---

## Stack

Python 3.12 · FastAPI · SQLAlchemy 2.0 async · Alembic · PostgreSQL 16 ·
pgvector · Ollama · Next.js 16 · React 19 · TypeScript · Tailwind v4 ·
TanStack Query

---

## License

MIT — see [LICENSE](LICENSE).
