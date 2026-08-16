# GUMMY OS — Backend

FastAPI service for the memory engine, conversations, goals, files, and the
agent runtime. Canonical description of the current system:
[M9 — Local-First GUMMY](../docs/10_RELEASE_NOTES_M9_LOCAL_FIRST.md).

> **Status:** M9 — runs entirely on one machine. Local Postgres, local models,
> local auth. Every hosted service is optional and off unless keyed.

---

## Requirements

- Python **3.12+**
- Docker (for Postgres 16 + pgvector) — `docker compose up -d db` from the repo root
- [Ollama](https://ollama.com) with `qwen2.5:3b` and `nomic-embed-text` pulled
- [`uv`](https://docs.astral.sh/uv/) (recommended) — or plain `pip`

## Quick start

```bash
cd backend
cp ../.env.example .env          # PowerShell: Copy-Item ..\.env.example .env
uv sync --all-extras
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Then open:
- Health: http://localhost:8000/health
- Swagger UI: http://localhost:8000/docs

Set `GUMMY_OWNER_MODE=true` in `.env` to skip the login wall on a single-user
machine. For a login flow instead, `POST /api/v1/auth/signup`.

<details>
<summary>pip alternative</summary>

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate     macOS/Linux:  source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env
uvicorn app.main:app --reload --port 8000
```
</details>

## Quality checks (must pass — mirrors CI)

```bash
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest                    # 655 passed, 4 skipped (Postgres-gated)
```

Tests run on in-memory SQLite and need no database or model server.

## Database migrations (Alembic)

Migrations need a real Postgres connection. Set `DATABASE_URL` and
`DIRECT_DATABASE_URL` in `.env`, then:

```bash
uv run alembic upgrade head            # apply all migrations
uv run alembic current                 # show the applied revision
uv run alembic downgrade -1            # roll back one revision
uv run alembic revision --autogenerate -m "describe change"   # new migration
```

Preview the SQL without touching a database (works offline):

```bash
uv run alembic upgrade head --sql
```

> Alembic reads the database URL from app settings (`migrations/env.py`), not
> from `alembic.ini`. It prefers `DIRECT_DATABASE_URL`, which connects as the
> owner role; the app itself connects as `gummy_app`, which is `NOBYPASSRLS`, so
> an application bug cannot read across tenants.

## Run with Docker

```bash
cd backend
docker build -t gummy-os-backend .
docker run --rm -p 8000:8000 --env-file .env gummy-os-backend
```

## Project layout

```
backend/
├── app/
│   ├── main.py              # app factory + entrypoint (uvicorn app.main:app)
│   ├── api/v1/              # auth, conversations, memories, goals, files,
│   │                        #   agents, search, connectors, health
│   ├── core/                # config, security (JWT), logging, exceptions
│   ├── database/            # async session, RLS GUC, Alembic migrations
│   ├── models/ schemas/     # SQLAlchemy 2.0 ORM + Pydantic v2
│   ├── repositories/        # data access, user-scoped
│   ├── services/
│   │   ├── auth/            # local token issuer, Google OAuth
│   │   ├── memory/          # instant recall, consolidation, timeline, profile
│   │   ├── conversation/    # turn service, summaries, emotion
│   │   ├── agents/          # router, orchestrator, policy, tools
│   │   ├── llm/ embeddings/ # Ollama (default), OpenAI, Claude, fake
│   │   └── connectors/      # iCal import
│   ├── observability/       # local analytics + optional Langfuse tracing
│   └── workers/             # background enrichment (memory extraction)
├── tests/
└── pyproject.toml           # deps + Ruff/Black/mypy/pytest config
```

## Environment

Configuration is loaded from `.env` (see the root [`.env.example`](../.env.example),
which documents every key). Unknown keys are ignored, so copying it wholesale is
safe. The defaults are fully local: Ollama for chat and embeddings, local
Postgres, GUMMY-issued JWTs. OpenAI and Anthropic keys are read only when
`LLM_PROVIDER` selects them.
