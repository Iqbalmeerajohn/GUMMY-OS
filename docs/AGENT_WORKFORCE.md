# The Agent Workforce

Four primary agents on one runtime. This describes what exists today; anything
not implemented is marked as such.

---

## 1. One runtime, six specialists

Every agent runs the same path. There is no per-agent orchestrator, memory
store, RAG layer, or tool system.

```
user → chat (streamed) → Master Orchestrator → Router → agent
                                                   ↓
                            unified knowledge (memories + goals + files)
                                                   ↓
                                    tool loop (registry → policy → executor)
                                                   ↓
                                        response → memory extraction → persist
```

| Agent | Purpose | Tools |
| --- | --- | --- |
| **Career** | Jobs, internships, scholarships, exams, certifications, hackathons, resumes, interviews, skill gaps | base + `web_search` |
| **Learning** | Explanations, learning plans, curricula, practice, progress | base + `web_search` |
| **Research** | Research plans, source collection, comparison, synthesis, citations | base + `web_search` |
| **Automation** | Reminders, recurring check-ins, summaries — local to GUMMY | `current_time`, `memory_read`, `automation_create`, `automation_list` |
| Planner | Goals, milestones, timelines | base |
| Memory | What GUMMY knows about the user | base |
| General | Everything else (routing fallback) | base |
| Recall | Deterministic memory digest (no model call) | `memory_read` |

*base* = `calculator`, `current_time`, `memory_read`, `file_search`, `file_list`

**Tool ceilings are enforced**, not advisory. A tool an agent does not declare
is refused by the policy engine before it runs, and a test asserts every
declared tool exists and sits within its agent's tier.

---

## 2. Agent identity lives in prompts

`services/agents/prompts/<agent>_agent_prompt.py` exports
`build_persona(message, knowledge) -> str`. That is the *only* per-agent code.
Grounding, ranking, tool execution, and persistence are shared.

Adding an agent = a manifest + a persona + a routing keyword set. No runtime
change.

**One persona is not pure**: the Automation Agent's stamps the current date and
time into its prompt. See §5.

---

## 3. Routing

Deterministic keyword scoring, no LLM call, no cost. Manual override works;
an unknown override degrades to General rather than failing.

```
"Find AI/ML fresher opportunities"   → career      (0.84)
"any good scholarships for me?"      → career      (0.72)
"I want to learn LangGraph deeply"   → learning    (0.72)
"Research the AI agent market"       → research    (0.84)
"Remind me tomorrow at 9am"          → automation  (0.95)
"What is the capital of France?"     → general     (0.30)
```

Career's keyword set was widened after live testing: *"Find AI/ML fresher
opportunities"* matched nothing and fell through to General, because the
canonical nouns (`job`, `resume`) are not how the request usually arrives. It
now spans the capabilities the agent claims — opportunities, freshers,
placements, scholarships, certifications, hackathons, exams.

---

## 4. Memory and knowledge

Both are shared, and unchanged by this milestone.

- **One memory engine.** No `career_memory` / `learning_memory`. Agents differ
  in what they *ask for*, not in where it lives.
- **Relevance-gated.** A memory must clear a measured semantic floor (0.45)
  before it can enter any agent's prompt, so memory stays silent unless it
  bears on the question. Verified live: "What is the capital of France?"
  injects zero memories.
- **One knowledge seam.** Memories + goals + files are fused, ranked, and
  token-budgeted by the M7 engine; search is supplemental and weighted below
  the user's own knowledge.

---

## 5. Automation: durable local scheduling

The only genuinely new subsystem in this milestone.

### Why it is not a queue

`embedding_worker` and `enrichment_worker` are in-memory `asyncio.Queue`s.
That is fine for work re-derivable from committed data. A reminder is not: if
"remind me tomorrow at 9" lives only in a process's memory, a restart loses it
with no error and no record.

So the schedule is a table, and the scheduler is a poller over it. No new
infrastructure — the database already running is the durable store.

### Tables

`automations` — the definition (kind, schedule, next_run_at, status, payload).
`automation_runs` — one row per firing, **unique on
`(automation_id, scheduled_for)`**.

That constraint is the idempotency mechanism. Claiming a slot means inserting
its run row, so two workers racing, a restart replaying a window, or a clock
stepping backwards all produce a constraint violation rather than a duplicate
reminder. A SAVEPOINT contains the losing insert so the batch continues.

Both tables are RLS-scoped, fail-closed.

### Scheduler

`workers/automation_scheduler.py`, 30s poll — also the worst-case lateness of
any task. It ticks immediately on startup, which is the restart-recovery path:
anything due while the process was down is already in the table and fires now.

It reads on the **owner connection**, like authentication, because it runs as
the system with no acting user and RLS would hide every row. Everything it then
executes is scoped to each automation's own `user_id`.

### Schedules

`once` · `daily` · `weekly`. The next slot is computed from the automation's
**anchor**, not from when the run happened — otherwise a 9am reminder that ran
at 9:40 drifts later every day until it leaves the morning entirely. A long
dormant schedule catches up in one step rather than looping per interval.

### The clock problem

A language model has no clock. Asked to schedule "tomorrow at 9", it computes
the date from its training cutoff. Observed live: `automation_create` was
called with a timestamp well in the past, the tool correctly refused it, and
the user got an apology instead of a reminder.

`current_time` exists as a tool, but call-then-hold-then-compute is a chain
with three places to fail on a 3B model. The current time is now stamped into
the Automation persona, so the fact is present before it is needed. Verified
live: "Remind me tomorrow at 9 AM" now persists `next_run_at = tomorrow 09:00`.

### What it does NOT do

Automations produce a message inside GUMMY. They **do not send email, create
calendar events, or touch anything outside the machine** — no such connector is
configured. Both the persona and the tool's own output say so explicitly,
because a model asked to "remind me" will otherwise confirm having emailed you.

---

## 6. Honesty rules, and how they are enforced

| Rule | Enforcement |
| --- | --- |
| No fabricated web results | `web_search` returns UNAVAILABLE without a live provider rather than relaying the offline placeholder's mock rows |
| No fabricated jobs | Career grounds in memories/goals/files; with no search it says so (verified live) |
| No claimed external actions | Automation persona + tool output both state the limitation; a test asserts the rendered output never claims email/calendar |
| No invented files | `file_list` before claiming a file exists |
| No chain-of-thought | Only `status` and `tool_status` events reach the client — a stage name, a tool key, a label. A test asserts the exact key set |

---

## 7. Multi-agent delegation

The orchestrator **supports** pipeline and parallel plan shapes, with A2A hops
persisted to `agent_messages` and per-step rows in `agent_steps`. Findings from
an earlier step are folded into the next step's prompt.

**Implemented.** The router detects compound requests grammatically — a
connective separating clauses that resolve to different specialists — and emits
a pipeline. *"Find AI jobs and then a learning plan for the biggest gap"* runs
Career → Learning, with the upstream findings handed forward as a structured
`AgentHandoff`. Verified live. See
[MULTI_AGENT_DELEGATION.md](MULTI_AGENT_DELEGATION.md).

Parallel plans remain un-routed: `_run_parallel` works and is tested, but no
keyword pattern produces a `PARALLEL` shape.

---

## 8. Verification

Backend **780 passed, 4 skipped, 0 failed**. Frontend typecheck, lint, tests
clean.

Live, against Postgres + Ollama over HTTP — **13/14**:

| Check | Result |
| --- | --- |
| Career routing + no fabricated listings | ✅ |
| Learning routing + structured plan | ✅ |
| Research routing + honest about unavailable search | ✅ |
| Automation routing → `automation_create` → persisted row | ✅ |
| `next_run_at` = tomorrow 09:00 (clock correct) | ✅ |
| Pause / resume | ✅ |
| Tenant isolation on automations | ✅ |
| Memory silent on an unrelated question | ✅ |
| **Survives backend restart** | ✅ verified by restarting and re-querying |

The 14th was an over-narrow assertion in the test script (the agent *was*
honest; the script's phrase list missed "is not available").

---

## 9. Known limitations

- **Parallel routing** — `_run_parallel` works and is tested, but no keyword
  pattern produces a `PARALLEL` plan. Sequential pipelines are routed (§7).
- **Automations run only while GUMMY is running.** The scheduler is in-process;
  a task due while the backend is stopped fires on next startup, not at its slot.
- **No notification channel.** A fired automation writes a run row visible in
  the panel; nothing pushes it to the user.
- **No connectors.** Gmail, Calendar, GitHub, Slack are not implemented. The
  `Signal`/`ingest` seam exists (calendar `.ics` import) but no OAuth token store.
- **Live web search** is config-gated (`TAVILY_API_KEY` + flag). Without it every
  agent honestly reports unavailability.
- **File RAG is hybrid.** `file_search` fuses vector similarity with Postgres
  full-text and gates results on a calibrated relevance floor, so "nothing
  relevant" is an outcome it can report. `doc_read` reads a named document.
- **Approval-gated actions** record the decision but do not execute; no Yellow
  or Red tool has an executor.
- **Timezone** is stored per automation but scheduling arithmetic is UTC-only.
