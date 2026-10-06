# Contributing to GUMMY OS

Thanks for looking. This is a personal project built in the open — issues,
questions and pull requests are all welcome.

Before anything else, read [`CONVENTIONS.md`](CONVENTIONS.md). It is the house
style, and it is short.

## Getting it running

```bash
git clone https://github.com/Iqbalmeerajohn/GUMMY-OS.git
cd GUMMY-OS
```

**Windows** — one command, from a cold machine:

```bash
gummy
```

**macOS / Linux**, or if you prefer the pieces:

```bash
docker compose up -d
cd backend && cp .env.example .env && uv sync --extra dev && uv run alembic upgrade head && uv run python scripts/serve.py
```

```bash
cd frontend && npm install && npm run dev
```

You need Docker, Python 3.12, Node 22, and [Ollama](https://ollama.com) with
`qwen2.5:3b` and `nomic-embed-text` pulled. The app is at
<http://localhost:3000>, the API at <http://localhost:8000/docs>.

## The checks CI runs

Run these before opening a PR. They are the exact commands CI uses, and they
are the whole contract:

```bash
cd backend && uv run ruff check . && uv run black --check . && uv run mypy app && uv run pytest -q
```

```bash
cd frontend && npm run lint && npm run format:check && npx tsc --noEmit && npm test && npm run build
```

Two things worth knowing, because both have bitten this repo:

- `black --check .` covers the **whole backend**, not just `app/` and `tests/`.
- Prettier is a gate on the frontend, and nothing reminds you about it.

`mypy app` blocks; `mypy tests` runs advisory. Test annotations are welcome
but are not a condition of merging.

## What makes a good pull request

**Small and explained.** The commit message should say *why*, not restate the
diff. Look at `git log` — messages here read as prose and explain the reasoning
and the trade-off. Match that.

**Tested against the failure, not the happy path.** For anything touching
tools, permissions or paths, the valuable test is the one that proves the
refusal works: the traversal that escapes, the URL that resolves to loopback,
the approval for a tool that no longer exists.

**Honest about what it does not do.** A PR that says "this does not handle X
yet" is better than one that implies it does.

## Things to be careful with

This project runs code on the user's machine, so a few areas need more thought
than usual:

- **Adding a tool.** Tools are code-defined in `tools/catalog.py` with a tier.
  Read-only and reversible is Green; anything that changes something is Yellow
  or Red and must go through the approval flow. If a tool takes a host path, it
  resolves through `tools/workspace.py` — never directly.
- **Raising an agent's ceiling.** A ceiling above Green is what lets a
  consequential tool be proposed at all. Exactly one agent has one today, and
  a test asserts that by name. Widening it should be a deliberate edit.
- **Negative tests are load-bearing.** A test asserting something *cannot*
  happen is a boundary, not an oversight. Superseding one means replacing it
  with a stronger assertion, not deleting it.

See [`SECURITY.md`](SECURITY.md) for the threat model these rules come from.

## Reporting bugs

Include what you ran, what happened, and what you expected. For anything
involving tools or permissions, the `tool_invocations` audit row (visible in
the Activity panel) is usually the most useful thing you can attach.

For security issues, please use a
[private advisory](https://github.com/Iqbalmeerajohn/GUMMY-OS/security/advisories/new)
instead of an issue.
