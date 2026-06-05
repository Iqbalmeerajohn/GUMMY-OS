# GUMMY OS — Engineering & Documentation Conventions

> Startup-grade discipline for a solo founder. These conventions keep GUMMY OS consistent,
> readable, and ready to scale to a team — and they apply **from Phase 0 onward**.

> **Status:** Locked for Phases 0–5. Revisit at the Phase 6 boundary or when the first
> additional contributor joins.

---

## 1. Folder Naming

- **Top-level project folders:** lowercase, single word where possible —
  `frontend/`, `backend/`, `docs/`, `architecture/`.
- **Source subfolders:** lowercase **kebab-case** — `memory-service/`, `agent-runtime/`.
- **Group by feature/domain, not by type** in application code (e.g. `career/`,
  `memory/`, `agents/`) once code exists — colocation beats scattering.
- **No spaces, no capitals, no underscores** in folder names.
- The repository folder is **`GUMMY-OS`** (rename the on-disk `IQBAL-OS` directory to match).

---

## 2. File Naming

| File kind | Convention | Example |
| --- | --- | --- |
| **Documentation (Markdown)** | Topic docs: `kebab-case.md`. Top-level "manifest" docs: `UPPER_SNAKE_CASE.md`. | `memory-system.md`, `VISION.md`, `FUTURE_AGENTS.md` |
| **Python modules** | `snake_case.py` | `memory_service.py` |
| **Python classes** | `PascalCase` (inside files) | `MemoryService` |
| **TypeScript/React components** | `PascalCase.tsx` | `MemoryCard.tsx` |
| **TS utilities/hooks** | `camelCase.ts` (hooks `useX.ts`) | `useMemoryStore.ts` |
| **Tests** | mirror source + suffix | `memory_service_test.py`, `MemoryCard.test.tsx` |
| **Config / env** | lowercase dotfiles | `.env.example`, `.editorconfig` |

- One primary export per file where reasonable; name the file after it.
- Never commit real secrets — only `.env.example` with placeholder keys.

---

## 3. Branch Naming

Pattern: `<type>/<short-kebab-description>` (optionally `<type>/<issue-id>-<desc>`).

| Type | Use |
| --- | --- |
| `feat/` | New feature | `feat/memory-retrieval-pipeline` |
| `fix/` | Bug fix | `fix/conversation-summary-overflow` |
| `docs/` | Documentation only | `docs/phase0-architecture` |
| `refactor/` | Restructure, no behavior change | `refactor/agent-contract` |
| `chore/` | Tooling, deps, config | `chore/ci-setup` |
| `test/` | Tests only | `test/memory-scoring` |

- `main` is always deployable. Never commit application code directly to `main`.
- Short-lived branches; rebase/merge promptly to avoid drift.

---

## 4. Commit Conventions

Follow **Conventional Commits**: `<type>(<scope>): <summary>`.

```
feat(memory): add confidence + importance scoring
fix(conversation): prevent rolling summary from exceeding token budget
docs(architecture): finalize Phase 0 security system
refactor(agents): extract typed agent task contract
chore(ci): add ruff + eslint to GitHub Actions
```

- **Imperative mood**, present tense ("add", not "added").
- Summary ≤ ~72 chars; body (optional) explains *why*, not *what*.
- One logical change per commit; keep history bisectable.
- Types: `feat`, `fix`, `docs`, `refactor`, `chore`, `test`, `perf`, `style`.
- Reference issues in the footer (`Refs #12`, `Closes #12`).

---

## 5. Documentation Standards

- **Markdown everywhere**; one concern per file.
- **Every doc opens with** a one-line purpose blockquote and a **Scope** note (what it does
  / doesn't cover, and its phase status).
- **Cross-link generously** using relative links (e.g. `[memory-system.md](...)`) — docs
  form a navigable web.
- **Tables for structured comparisons**; fenced code blocks for diagrams/flows.
- **Keep docs current:** a change that alters architecture updates the doc in the *same*
  PR ("docs travel with code").
- **Tone:** professional, concise, decision-oriented. State *why*, not just *what*.
- **Status discipline:** mark Locked / Planned / Future and add re-evaluation triggers.

---

## 6. Architecture Standards

- **Document decisions, not just outcomes** — for significant choices capture: why,
  alternatives considered, tradeoffs, future scalability (see
  [architecture/tech-stack.md](architecture/tech-stack.md) as the template).
- **Multi-tenant from day one** — every data path is `user_id`-scoped.
- **Stateless services, stateful stores** — no durable state in app code.
- **Clean seams** — Memory Service, LLM gateway, storage, and auth are abstractions with
  swappable implementations (no vendor lock-in at the interface).
- **Security by default** — every new action is classified Green/Yellow/Red before it ships
  (see [architecture/security-system.md](architecture/security-system.md)).
- **Scalability designed in, complexity added late** — no Kubernetes/microservices until
  warranted; favor the simplest thing that won't require a rewrite.

---

## 7. Coding Standards

> No application code exists yet (Phase 0). These rules take effect at Phase 1.

**General**
- Strong typing everywhere: **TypeScript** (frontend), **Python type hints + Pydantic**
  (backend).
- Prefer clarity over cleverness; small, single-responsibility functions.
- Comments explain *why*; let well-named code explain *what*.
- No magic numbers/strings — use named constants/config.
- Handle errors explicitly; never swallow exceptions silently.

**Python (backend)**
- Format with **Black**, lint with **Ruff**; line length 88–100.
- `snake_case` functions/vars, `PascalCase` classes, `UPPER_SNAKE` constants.
- Async-first for I/O (LLM, DB, network).

**TypeScript (frontend)**
- **ESLint + Prettier** enforced; `camelCase` vars, `PascalCase` components/types.
- Functional React components + hooks; colocate component, styles, and tests.

**Quality gates**
- Lint + format + type-check + tests run in CI on every push (see §8 of
  [tech-stack.md](architecture/tech-stack.md)).
- Meaningful tests for memory, scoring, retrieval, and permission logic (the risky core).

---

## 8. Pull Request Standards

- **Small, focused PRs** — one concern; easy to review (even solo — your future self
  reviews too).
- **PR title** follows Conventional Commits style.
- **PR description must include:**
  - **What** changed and **why**.
  - **Scope/phase** it belongs to.
  - **Testing** done (or why none).
  - **Docs updated?** (yes/no + which).
  - **Permission impact** — does it add/alter a Green/Yellow/Red action?
- **CI must be green** (lint, types, tests) before merge.
- **Self-review checklist** before requesting/merging:
  - [ ] No secrets committed.
  - [ ] Tenant-scoped (`user_id`) where data is touched.
  - [ ] Docs travel with the change.
  - [ ] New external actions classified in the permission model.
  - [ ] No unrelated changes.
- **Merge style:** squash-merge to keep `main` history clean and readable.

---

## 9. Definition of Done (any task)

A change is "done" only when it is:
1. **Implemented** to spec, typed, and clear.
2. **Tested** (where logic warrants) and CI-green.
3. **Documented** (docs updated in the same PR).
4. **Secure** (permission-classified, tenant-scoped, no secrets).
5. **Reviewed** (self-review checklist passed) and squash-merged to `main`.

---

_Related: [README.md](README.md), [architecture/tech-stack.md](architecture/tech-stack.md),
[architecture/security-system.md](architecture/security-system.md)._
