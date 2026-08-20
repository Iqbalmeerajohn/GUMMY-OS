# GUMMY OS — Résumé & Interview Summary

Only verified capabilities appear here. Every number is reproducible from
[VERIFICATION_REPORT.md](VERIFICATION_REPORT.md).

Deliberately **not** claimed: production, 24/7, cloud, fully autonomous, or any
accuracy percentage.

---

## One-line description

> A local-first personal AI operating system — persistent long-term memory,
> multi-agent orchestration, safe tool execution, and durable automation — built
> on FastAPI, PostgreSQL/pgvector, and local Ollama models, with no external
> service dependency.

---

## Résumé bullets

**Built a relevance-gated long-term memory engine on PostgreSQL + pgvector**
that extracts facts from conversation, consolidates them (restatements
reinforce; more specific versions supersede), and retrieves them by hybrid
ranking. Calibrated the retrieval threshold empirically against the live
embedding model — 0.45 semantic similarity rejects 96.5% of irrelevant memories
while retaining 92% of relevant ones — eliminating the "assistant volunteers
unrelated facts" failure mode.

**Built account recovery for a self-hosted identity provider**, with reset
tokens stored only as a SHA-256 hash, single-use via a `used_at` stamp,
45-minute expiry, and revocation of every session on the account at redemption.
`forgot-password` returns a byte-identical response for known and unknown
addresses, so it cannot be used to enumerate accounts. Because the product must
run with no cloud dependency, delivery is a mode rather than a dependency: the
default writes the link to the backend log, so the full flow is testable with no
provider and nothing ever reports an email as sent when none was.

**Designed a safe agent tool-execution loop** with a code-defined registry,
Green/Yellow/Red policy gate, JSON-Schema validation, per-tool timeouts, and a
bounded reason→call→observe cycle, backed by redacted audit rows. Arithmetic is
evaluated through an AST allowlist rather than `eval`, so code-execution
payloads are rejected at parse level — added after a local model was observed
passing Python to a calculator tool unprompted.

**Implemented deterministic multi-agent delegation** across six specialists on
one orchestrator: compound requests are detected grammatically (a connective
separating clauses that resolve to different agents) and executed as a pipeline
with structured hand-offs and persisted agent-to-agent traces, while
single-capability requests provably stay single-agent. Verified 19/19 routing
scenarios live.

---

## Engineering metrics

| Metric | Value |
| --- | --- |
| Backend tests | 947 passed, 4 skipped, 0 failed |
| Frontend tests | 18 passed, 0 failed |
| Static analysis | `ruff`, `black`, `mypy app` clean (241 files); TS + ESLint clean |
| Migrations | 25 |
| API | 73 endpoints, 15 routers |
| Agents | 6 routed specialists + general + recall |
| Tools | 9 executable, 2 modeled behind approval |
| Tenant tables under RLS | 25 |
| Live auth + isolation | 26/26 |
| Live password reset | 19/19 + browser round trip |
| Live parallel routing | shapes verified; 17-19 ms branch finish spread |
| Live routing | 19/19 |
| Live tool loop | 10/10 |

---

## Stack

Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · Alembic · PostgreSQL 16 ·
pgvector · Ollama (`qwen2.5:3b`, `nomic-embed-text`) · Next.js 16 · React 19 ·
TypeScript · Tailwind v4 · TanStack Query · Docker

---

## Interview talking points

**Why a relevance floor, and why 0.45.**
Semantic similarity was only 55% of the blended retrieval score, so importance
and recency could carry a topically unrelated memory into the prompt. The fix
gates on *raw* similarity, and the threshold was measured rather than guessed:
probe queries against real stored memories showed irrelevant pairs averaging
0.362 and relevant pairs 0.533. 0.50 would have been cleaner on precision but
discarded 42% of genuine recall — a forgetful assistant is a more visible
failure than an occasional stray fact.

**Making two code paths agree by construction.**
The streamed and non-streamed chat paths had drifted, and the richer one (the
orchestrator) was the one production never used. Rather than syncing them, the
streaming path became the single implementation and the non-streaming call
became a thin drain of it — divergence became impossible rather than
discouraged, and every existing test kept passing because the public signature
was preserved.

**Idempotency as a database guarantee.**
The automation scheduler claims a slot by inserting a run row with a unique
constraint on `(automation_id, scheduled_for)`. Two workers racing, a restart
replaying a window, or a clock stepping backwards all produce a constraint
violation instead of a duplicate reminder — correctness from a constraint rather
than from careful sequencing.

**A green test suite is not evidence about a real dependency.**
The hermetic suite used a fake model provider that returned well-formed JSON by
construction. Against the real local model, every memory extraction failed on
one missing quote — so the product's central feature had never worked, silently,
with no failing test. Fixed with constrained decoding at the source plus a
tolerant fallback.

**A convenience feature that was a data leak.**
"Owner mode" auto-authenticated requests on a single-user machine. Measured
against the running app, an anonymous caller received the owner's identity, 7
memories, and 10 conversations — and sign-out could not work by construction,
since the client discards its token and is told it is still the owner. The fix
gated the feature on its own premise: it applies only while the owner is the
sole account.

**A dangling link is a feature claim.**
The login screen had linked to `/forgot-password` since the day local auth
landed. There was no page, no endpoint, and no table behind it — clicking it
gave a 404. The documentation had honestly recorded "no password reset flow" as
a limitation, which is exactly why it survived: the gap was written down
somewhere nobody looked while the UI kept promising otherwise. Shipping the
feature meant treating the link, not the doc, as the specification.

**Defending against the model, not with it.**
The first probe of a local model with tools attached, asked only to say hello,
called the calculator with `print('Hello')`. A tool's safety cannot rest on the
model behaving well, so rejection is structural — an AST allowlist where calls,
names, and attributes are parse-level failures.

---

## Honest limitations

Google sign-in is configured and its entry point verified, but the full
round trip was not tested.
Password-reset email is console-mode locally; SMTP is implemented and
unit-tested but never sent against a real server.
File retrieval is keyword-based, not
vector RAG. Live web search is config-gated. No connectors, no public
deployment, no cloud infrastructure.
