# GUMMY OS — Backend

FastAPI service for the memory engine and (later) the agent runtime. See the
[Phase 1 build plan](../docs/phase-1-build-plan.md) for scope and the
[tech stack](../architecture/tech-stack.md) for the locked decisions.

> **Status:** Phase 1, Day 1 — scaffold only (app boots, config, health probes).
> No Memory Engine code yet.

---

## Requirements

- Python **3.12+**
- [`uv`](https://docs.astral.sh/uv/) (recommended) — or plain `pip`

## Quick start (uv — recommended)

```bash
cd backend
cp ../.env.example .env          # PowerShell: Copy-Item ..\.env.example .env
uv sync --all-extras             # install runtime + dev dependencies
uv run uvicorn app.main:app --reload --port 8000
```

Then open:
- Health:  http://localhost:8000/health
- Docs (Swagger UI):  http://localhost:8000/docs

> Day 1 runs **without a database**. The readiness probe reports
> `"database": "not_configured"` until a real `DATABASE_URL` is set (Day 2).

## Quick start (pip alternative)

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate     macOS/Linux:  source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env
uvicorn app.main:app --reload --port 8000
```

## Quality checks (must pass — mirrors CI)

```bash
uv run ruff check .
uv run black --check .
uv run mypy .
uv run pytest
```

## Run with Docker

```bash
cd backend
docker build -t gummy-os-backend .
docker run --rm -p 8000:8000 --env-file .env gummy-os-backend
```

## Project layout (Day 1)

```
backend/
├── app/
│   ├── main.py              # app factory + entrypoint (uvicorn app.main:app)
│   ├── api/
│   │   ├── deps.py          # shared dependencies (settings; auth/db added Day 2)
│   │   ├── router.py        # /api/v1 aggregate router
│   │   └── v1/health.py     # /health + /health/ready
│   ├── core/
│   │   ├── config.py        # pydantic-settings, loaded from .env
│   │   ├── logging.py       # structured JSON logging
│   │   └── exceptions.py    # error envelope + handlers
│   ├── database/session.py  # async engine + readiness ping (ORM lands Day 2)
│   ├── schemas/health.py    # health response models
│   ├── models/ repositories/ services/ utils/ workers/   # placeholder packages
├── tests/                   # health smoke tests
├── pyproject.toml           # deps + Ruff/Black/mypy/pytest config
├── requirements*.txt        # pip fallback
└── Dockerfile
```

## Environment

Configuration is loaded from `.env` (see the root [`.env.example`](../.env.example)).
Day 1 uses only the core/backend keys; database, Supabase, and Anthropic keys are
read on the days those integrations land. Unknown keys are ignored, so the shared
`.env.example` is safe to copy wholesale.
