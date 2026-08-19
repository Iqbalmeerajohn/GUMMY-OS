# Verification Report

Measured 2026-08-19 against the working tree at the commit this document ships
with. Every number here was produced by running the thing, not estimated.

There is no single "accuracy" figure for this project — it is not a classifier.
What follows is engineering evidence with exact denominators.

---

## 1. Automated checks

| Check | Command | Result |
| --- | --- | --- |
| Backend tests | `pytest -q` | **837 passed, 4 skipped, 0 failed** |
| Frontend tests | `npm test` | **11 passed, 0 failed** |
| TypeScript | `npm run typecheck` | **clean** |
| ESLint | `npm run lint` | **clean** |
| Python lint | `ruff check app tests` | **clean** |
| Formatting | `black --check app tests` | **clean** |
| Types (app) | `mypy app` | **clean — 235 source files** |
| Types (tests) | `mypy tests` | **57 errors in 23 files — pre-existing** |

The 4 skipped backend tests are Postgres-gated and do not run against the
in-memory SQLite suite.

**The 57 `mypy tests` errors are pre-existing** and sit in files untouched by
recent work (missing annotations on test helpers, mostly `no-untyped-def`). They
are reported rather than hidden. `mypy app` — which CI runs — is clean.

---

## 2. Live authentication and isolation — 26/26

Run against PostgreSQL + Ollama + FastAPI over real HTTP.

| # | Check | Result |
| --- | --- | --- |
| 1 | `GET /auth/me` with no token | 401 |
| 2–4 | memories / conversations / automations with no token | 401 each |
| 5 | `owner_mode` reported off | ✅ |
| 6 | User A signup | 201 |
| 7 | Display name "Test User A" preserved | ✅ |
| 8 | User A owns memory, conversation, goal | 1 / 1 / 1 |
| 9 | Sign-out accepted | 204 |
| 10 | Revoked refresh token replay | 401 |
| 11 | Anonymous request after sign-out | 401 |
| 12 | User B signup | 201 |
| 13 | Display name "Test User B" | ✅ |
| 14 | A and B are distinct accounts | ✅ |
| 15–17 | B sees A's memories / conversations / goals | **0 / 0 / 0** |
| 18 | B can create their own memory | ✅ |
| 19 | B fetching A's conversation by id | **404** |
| 20 | A can log in again | 200 |
| 21 | A's user id unchanged | ✅ |
| 22 | A's display name stable after re-login | ✅ |
| 23 | A's data survived the switch | ✅ |
| 24 | A does not see B's memory | ✅ |
| 25 | `google_enabled` false when unconfigured | ✅ |
| 26 | `google/start` unconfigured | 503, no crash |

**Before the fix**, checks 1–4 returned **200** — an anonymous caller was served
the owner's identity, 7 memories, and 10 conversations.

---

## 3. Live multi-agent routing — 19/19

The persisted `route_plan` is the authority, not the event stream.

| Request | Plan | Latency |
| --- | --- | --- |
| "Find AI/ML fresher opportunities suitable for me." | `single [career]` | 9.0 s |
| "Teach me LangGraph from beginner to advanced." | `single [learning]` | 7.7 s |
| "Research the AI agent landscape." | `single [research]` | 10.7 s |
| "Remind me tomorrow at 9 AM to review my goals." | `single [automation]` | 14.0 s |
| "…jobs **and** a learning plan for the biggest skill gap." | `pipeline [career, learning]` | 17.3 s |
| "Research LangGraph **and then** teach me…" | `pipeline [research, learning]` | 22.5 s |
| "Find jobs, research the companies, and how to prepare." | `pipeline [career, research]` | 30.4 s |

Trace for the Career → Learning turn: 2 steps both `succeeded`, **4 A2A hops**,
no reasoning in any payload, **404** for another tenant's run id.

---

## 4. Live tool loop — 10/10

| Check | Result |
| --- | --- |
| "What is 123 × 456?" | calculator ran → **56088**, 10.3 s |
| Fact stated, asked in a **new** conversation | recalled correctly |
| "Do I have any files?" | `file_list` ran, invented nothing |
| "Search the web for…" | reported unavailable, fabricated nothing |
| Date **+** 15% of 2400 | two tools in one turn |
| `__import__('os').system(...)` as an expression | `tool_failed`, nothing executed |

---

## 5. Live automation

| Check | Result |
| --- | --- |
| "Remind me tomorrow at 9 AM" | persisted, `next_run_at = tomorrow 09:00` |
| Pause / resume | ✅ |
| Tenant isolation on automations | ✅ |
| **Survives a backend restart** | ✅ verified by restarting and re-querying |

---

## 6. Project inventory

| Metric | Value |
| --- | --- |
| Alembic migrations | 24 |
| API routers | 15 |
| API endpoints | 71 |
| Backend test files | 100 |
| Agent manifests | 8 (6 routed specialists + general + recall) |
| Tools defined | 11 |
| Tools executable | 9 (2 modeled behind approval) |
| Max tool iterations per turn | 4 |
| Max compound pipeline steps | 3 |
| Memory relevance floor | 0.45 semantic similarity |
| Tenant tables under RLS | 24 |

---

## 7. Capability matrix

| Capability | Status | Evidence |
| --- | --- | --- |
| Email signup / login | **Working** | 26/26 live; 22 automated |
| Sign-out | **Working** | live 9–11; refresh replay → 401 |
| Session refresh + rotation | **Working** | automated |
| Multi-user isolation | **Working** | live 15–19, 24; RLS on 24 tables |
| Display name handling | **Working** | live 7, 13, 22 |
| **Google sign-in** | **Implemented, unverified** | code complete; **no credentials configured — not tested end to end** |
| Persistent memory | **Working** | live recall across conversations |
| Memory relevance gating | **Working** | calibrated 0.45; 0 injected for unrelated query |
| Silent memory | **Working** | no narration in live replies |
| Memory consolidation | **Working** | superseded row in live data |
| Unified chat → orchestrator | **Working** | `agent_runs` recorded per streamed turn |
| Tool registry / policy / executor | **Working** | 50 automated + 10/10 live |
| Bounded tool loop | **Working** | 4-iteration cap tested |
| Calculator safety | **Working** | 10 hostile inputs rejected at parse level |
| File search | **Working (keyword)** | ILIKE substring; **no vector RAG** |
| **Vector file RAG** | **Not implemented** | no `file_chunk_embeddings` table |
| Career / Learning / Research agents | **Working** | live routing + replies |
| Automation Agent | **Working** | creates real persisted records |
| Automation persistence | **Working** | survived a restart |
| Pipeline delegation | **Working** | 3 pipelines live, A2A traced |
| **Parallel routing** | **Not started** | `_run_parallel` exists and is tested; no keyword produces a `PARALLEL` plan |
| **Live web search** | **Config-gated** | Brave client complete; no key → reports unavailable |
| **Connectors** | **Calendar only** | `.ics` import; no OAuth token store |
| **Cloud deployment** | **Not provided** | intentionally local-only |

---

## 8. Security verification

| Property | Verified |
| --- | --- |
| Anonymous requests rejected | ✅ live 1–4 |
| Cross-user memory / conversations / goals | ✅ live 15–19 |
| Direct-id access to another user's record | ✅ 404 |
| Another tenant's agent-run trace | ✅ 404 |
| RLS enforced at the database | ✅ `gummy_app` is `NOBYPASSRLS`; 24 tables |
| No arbitrary code execution | ✅ AST allowlist; `eval` never used |
| No shell execution | ✅ no tool spawns a process |
| Tool ceilings across a pipeline | ✅ automated |
| Secrets never committed | ✅ scan clean; `.env` gitignored |
| Secrets redacted in audit rows | ✅ automated |
| No chain-of-thought in traces or events | ✅ automated |

---

## 9. What is explicitly NOT claimed

- **Google sign-in has not been tested end to end.** The code path is complete
  and the UI hides itself correctly, but no credentials exist on this machine.
- **No public deployment.** GUMMY runs locally; `localhost` URLs are not
  reachable by anyone else.
- **No parallel agent routing.**
- **No vector file RAG.**
- **No accuracy percentage.** Nothing here was benchmarked against a labelled
  dataset, so no such number is offered.
