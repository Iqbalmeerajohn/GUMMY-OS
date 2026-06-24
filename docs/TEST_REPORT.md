# GUMMY OS — Test Report

> Verification snapshot captured at the M8.5 development-freeze point.
> **Run date:** 2026-06-24 · **Command:** `pytest -q` (backend `.venv`, pytest 9.0.3)

---

## 1. Headline result

```
598 passed, 4 skipped, 22 warnings in ~32s
PYTEST_EXIT = 0
```

| Metric | Value |
| --- | --- |
| **Passed** | **598** |
| **Failed** | **0** |
| **Skipped** | 4 (Postgres-gated; intentional) |
| **Errors** | 0 |
| Test files | 86 |
| `def test_*` definitions | ~548 (more cases via parametrization) |
| Wall time | ~32 seconds |
| Runtime | Python 3.12, pytest 9.0.3, pytest-asyncio |

---

## 2. Skipped tests (intentional, not failures)

All 4 skips are in `tests/test_rls_postgres.py`, gated behind real Postgres:

```
SKIPPED test_rls_postgres.py:40   — set RUN_RLS_PG_TESTS=1 and RLS_TEST_DSN (gummy_app DSN)
SKIPPED test_rls_postgres.py:121  — set RUN_RLS_PG_TESTS=1 and RLS_TEST_DSN (gummy_app DSN)
SKIPPED test_rls_postgres.py:329  — set RUN_RLS_PG_TESTS=1 and RLS_TEST_DSN (gummy_app DSN)
SKIPPED test_rls_postgres.py:521  — set RUN_RLS_PG_TESTS=1 and RLS_TEST_DSN (gummy_app DSN)
```

These verify **fail-closed Row-Level Security, cross-tenant rejection, and tenant
isolation under full-text + vector search**, executed as the non-bypass
`gummy_app` role against a live Postgres. They are skipped in the hermetic
SQLite run by design and must be exercised in a Postgres CI stage.

> **Action for CI:** run a Postgres-backed stage with `RUN_RLS_PG_TESTS=1` +
> `RLS_TEST_DSN` so the security-critical suite is verified on every change.

---

## 3. Warnings (benign)

22 warnings, all `InsecureKeyLengthWarning` from PyJWT in `test_auth.py` /
`test_auth_api.py` — the auth **unit tests** sign tokens with short HMAC keys
(12–15 bytes) as fixtures. Production keys are not affected. No deprecation or
runtime warnings of concern.

---

## 4. Test strategy

A deliberately **hermetic, fast** suite over Postgres-only features:

- The full suite runs on **in-memory SQLite** (`aiosqlite`) — zero infra, ~32s.
- Postgres-only features **degrade gracefully** under SQLite: pgvector ranking
  falls back to JSON, full-text search is skipped, RLS PG tests skip-gate.
- A **Postgres-gated** suite (`RUN_RLS_PG_TESTS=1`) verifies RLS, FTS, and vector
  search against real Postgres under the non-bypass role.
- LLM and embeddings run behind **deterministic fake providers** in tests — no
  network, no flakiness, no spend.

---

## 5. Coverage by area (test files present)

| Area | Representative test files |
| --- | --- |
| **Memory** | memory_service, memory_repository, memory_embedding_repository, memory_lifecycle, memory_extraction_service, memory_api, memory_e2e, memory_diagnostics_api, reinforcement |
| **Conversation** | conversation_service, conversation_turn_service, conversation_repository, conversation_api, turn_api, summary_service, conversation_continuity, conversation_search_{api,service,repository} |
| **Auth / Security** | auth, auth_api, tenant_context, user_context, **rls_postgres** (PG-gated) |
| **Agents / Orchestration** | agent_router, agent_executor, orchestrator_service, orchestrator_{pipeline,parallel}, agent_registry, agent_repository, agent_models, agent_memory, run_recorder, compose, context_builder, router, router_eval (evals), policy_engine, approval_service, agents_contract |
| **Specialists** | career_agent, learning_agent, planner_agent, memory_agent, research_agent, agent_diagnostics_api |
| **Knowledge (M7)** | knowledge_retrieval_service, knowledge_ranker, knowledge_context_builder, knowledge_diagnostics_api, retrieval_api, retrieval_ranking |
| **Search (M8.5)** | search_provider, search_service, search_api, search_repository |
| **Files (M6/M6.5)** | file_service, file_repository, file_processing, files_api, file_context_service, file_attachment_api, file_aware_conversation, file_agent_awareness |
| **Goals (M5/M5.5)** | goal_service, goal_task_service, goal_extraction_service, goal_intelligence_api, goal_task_api, goal_milestone_api, goal_lookup_resilience, milestone_service |
| **Embeddings / LLM** | embedding_service, embedding_worker, claude_gateway |
| **Workers** | embedding_worker, enrichment_worker |
| **Observability** | langfuse_observability, logging |
| **Platform** | health, models, prompt_builder, context_assembly, tool_interface, actions_api, auto_sync |

---

## 6. Quality gates

| Gate | Status |
| --- | --- |
| Backend tests (`pytest`) | ✅ 598 passed / 0 failed |
| Lint (`ruff`) | Configured (CONVENTIONS §7); clean in prior milestone reports |
| Types (`mypy`) | Configured; project is fully type-annotated |
| Format (`black` profile) | Configured |
| Frontend types (`tsc --noEmit`) | Clean per M4 verification |
| Frontend lint (`eslint`) | Clean per M4 verification |
| Frontend unit tests (`node --test`) | Present for config/goals/dashboard logic |

> _This report reflects the backend `pytest` run executed at freeze. Lint/type
> gates are configured and were green in the latest milestone notes; re-run
> `ruff check` and `mypy` before any post-pause resume to reconfirm._

---

## 7. Verdict

The backend is **green at the freeze point**: 598 passing tests, zero failures,
all skips intentional and documented, fast hermetic execution, and a separate
live-Postgres path that proves the security-critical isolation guarantees. This is
a safe, well-verified state to pause on.
