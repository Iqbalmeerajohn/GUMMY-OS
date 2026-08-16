# M9 — Local-First GUMMY

**Date:** 2026-08-12 · **Supersedes the M8.5 freeze**

GUMMY now runs entirely on the user's machine, answers instantly for the things
it already knows, and maintains a portrait of the person rather than a pile of
facts. This note is the canonical record of what changed; earlier documents that
describe Supabase, Railway, Vercel, Sentry, or PostHog describe the pre-M9
system and are kept only as history.

---

## 1. Why local-first

The product promise is "it remembers you". Every hosted dependency was a
contradiction of that promise and a running cost:

| Was | Now | Why it matters |
| --- | --- | --- |
| Supabase (auth + Postgres) | Local Postgres 16 + pgvector, GUMMY-issued JWTs | The memory of a person's life should not require someone else's account |
| Railway (backend) | `uvicorn` on localhost | No deploy, no cold start, no bill |
| Vercel (frontend) | `next dev` / `next build` locally | Same |
| Sentry + PostHog | Local structured logging (`app.core.observability`, `app.observability.analytics`); both SDKs removed from `pyproject.toml`, `requirements.txt`, and `package.json` | Behavioural telemetry about a memory product is the one thing that must never leave the device |
| Hosted embeddings | Ollama `nomic-embed-text` (768-d) | Free, offline, and no text ever leaves the machine |
| Hosted chat model | Ollama `qwen2.5:3b`, OpenAI/Claude keys still supported | Free by default; the paid path stays available for hard questions |

Nothing about tenancy was weakened to get here. Row-Level Security is unchanged
and still fail-closed: every table carries a policy keyed on the per-transaction
`app.current_user_id` GUC, and the application role cannot bypass it.

"Disabled by default" was not treated as good enough. A dormant SDK is still a
dependency to audit, a key someone can paste in by accident, and a claim in the
README that is only conditionally true — so the code, the settings, and the
packages all came out. What remains is `capture_exception()` and
`capture_event()`, which write structured lines to the local log with the same
call signatures, so the ~20 call sites and their tests are untouched. Langfuse is
the one integration kept: it is opt-in, needs two keys, and `LANGFUSE_HOST` can
point at a self-hosted instance, so tracing an LLM call never implies shipping it
anywhere.

---

## 2. Auth — GUMMY is its own identity provider

* **Email + password** (`POST /api/v1/auth/signup`, `/login`) issuing HS256 JWTs
  with audience `gummy-os`. This is now the *only* issuer: the Supabase HS256/
  JWKS verifier, its settings, and its JWKS client are deleted. One issuer and
  one algorithm means no key routing, and therefore no algorithm-confusion
  surface to defend.
* **Rotating refresh tokens**, stored hashed. Rotation revokes the presented
  token, so a stolen copy dies the moment the real client refreshes.
* **Google OAuth** (`/auth/google/start` → `/auth/google/callback`) using the
  authorization-code flow with a signed-JWT `state`. Tokens come back in the URL
  **fragment**, which browsers never send to servers and which never appears in
  logs or `Referer` headers.
* **Owner mode** (`GUMMY_OWNER_MODE=true`) signs every request in as the local
  owner, for a single-user machine that should never see a login screen.
* `GET /api/v1/auth/config` tells the client which methods exist, so the login
  screen never offers a Google button the server has no credentials to honour.

Google sign-in stays hidden until `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
are set, with redirect URI `http://localhost:8000/api/v1/auth/google/callback`.

---

## 3. Speed — answering without generating

Generation costs ~2–3 s to first token whether it comes from the local GPU or a
hosted API; prompt tuning does not remove that. Sub-second recall is therefore
only reachable by **not generating**.

**Instant recall** (`app/services/memory/instant_recall.py`) answers direct
questions about stored facts ("what's my name", "where do I live") straight from
memory. Three independent gates must all pass — known intent, a matching stored
fact, and a clear margin over the runner-up — and when in doubt it declines,
costing one wasted lookup and falling through to the normal path. A confidently
wrong instant answer would be a visible product failure; a decline is invisible.

The fast path runs **before** query embedding, since embedding is itself part of
the latency being avoided.

Measured on this machine against the live stack (Postgres in Docker, Ollama
`qwen2.5:3b`), over HTTP including persistence and commit:

| Turn | Model | Wall clock |
| --- | --- | --- |
| "where do I live?" (instant) | none | **584 / 602 / 670 / 1105 ms** across four runs |
| "what am I building?" (two competing facts → declined) | qwen2.5:3b | 6.7 s |
| "what should I focus on this week?" (genuinely generative) | qwen2.5:3b | 2.9 s |

The lookup itself is a few milliseconds; the rest is the turn's own database
work. The decline in the middle row is the design working, not a miss: two
stored project facts answered equally well, so the model reconciled them.

**Both** turn paths take it. Instant recall was wired into the streamed turn
first; the non-streaming `POST /conversations/{id}/messages` still spent ~2.5 s
having a model repeat a fact already on disk. That gap was found by running the
real server rather than the test suite, and is now closed and covered by
`test_run_turn_answers_a_recall_question_without_the_model`.

---

## 4. Memory — from a fact store to a portrait

Four layers now sit on top of the memory engine:

**Consolidation** (`consolidation.py`) — every incoming fact is checked against
what is already stored before it is written. A restatement reinforces the
existing memory; a more specific version supersedes it (status `superseded`, not
deleted, so history stays auditable). Similarity uses Postgres trigrams, not
embeddings, because this runs on the *write* path and an embedding call there
would add a round-trip to every fact saved.

**Learned profile** (`user_profile_service.py`, table `user_profiles`) — one row
per user holding the traits GUMMY has settled on (name, location, work, project),
how the person writes, and their emotional baseline. Maintained in two rhythms:
`observe()` on the hot path is a primary-key fetch plus arithmetic, while
`refresh_traits()` re-derives traits from active memories off the hot path. The
traits are *derived*, never stored twice — so a corrected or archived memory
updates the portrait for free.

**Episodic timeline** (`timeline.py`, `memories.occurred_at`) — when a remembered
thing *happened*, as opposed to when it was written down. Without it "what did I
do last week?" is unanswerable, since a note taken today about last Tuesday sorts
as today. Past-tense phrases ("yesterday", "last Monday", "3 weeks ago") are
parsed at extraction time; retrospective questions are matched to a date window
and served by a partial index. Future phrases are ignored on purpose — those are
goals, and goals already have their own model.

**Reinforcement and decay** — retrieval scores combine semantic similarity,
importance, confidence, and a recency half-life; recalled memories are reinforced
under a cooldown so a chatty topic cannot saturate the ranking.

---

## 5. Tone — friendly, and still working

`app/services/conversation/emotion.py` reads the emotional register of each
message from a small lexicon and turns it into one system-prompt line: lead with
the answer when the user is under time pressure, skip the apologies when
something keeps breaking, keep next steps small when they sound worn out.

It is a lexicon and not a classifier because it runs before the first token on
every turn — a model call here would cost more than the reply it shapes, and a
wrong guess only costs a slightly-off greeting.

Mood is a property of a *message*, never stored as a fact about the user; only
the aggregate baseline reaches the profile, and only once there is enough
evidence to mean something.

All three — profile, timeline, tone — are folded into the prompt by one
best-effort helper, `_personalize()` in `conversation_turn_service`. Any failure
degrades to the plain identity block: personalization improves a reply, it must
never be the reason there isn't one.

---

## 6. Connectors — the user's own data

`POST /api/v1/connectors/calendar` imports past events from a Google Calendar
**secret iCal address** (or any `.ics` file). That form was chosen over the
Calendar API deliberately: no OAuth scopes, no token storage, no app review — it
works on a machine that talks to nothing else, and the same parser covers Apple
Calendar, Outlook, and Google Takeout exports.

Imported events land as memories with `occurred_at` set, which is what makes the
timeline reflect the user's real week rather than only what they typed into chat.
Re-importing is safe: consolidation reinforces rather than duplicates.

Gmail, Maps/location history, and Drive are **not** implemented. They need
stored OAuth tokens with incremental scopes and a refresh flow, which is its own
milestone — see §9.

---

## 7. Interface — the chat *is* the app

The web client went from 24 routes to 6 (`/`, `/login`, `/signup`,
`/auth/callback`, `/icon.svg`, `/_not-found`). `/` is the chat when signed in and
a landing page when not.

Everything that used to be a page is now a slide-over panel behind a 56 px icon
rail: Chats, Search (⌘K), Memory, Goals, Files, Agents, Settings. Deleted
outright: about-gummy, future, updates, voice, automation, dashboard, onboarding,
welcome, workspace.

The Agent Directory now states the truth about the backend: the five routed
specialists plus general and recall are marked **Available**; everything else —
workflow, content, marketing, sales, business, admin — sits in the plan phase
with a **Planned** badge, so the directory never implies capability that is not
there.

---

## 8. Verification

| Check | Result |
| --- | --- |
| Backend suite | **655 passed**, 4 skipped (Postgres-gated), 0 failed |
| New tests | instant recall, consolidation, user profile, timeline, emotion, local auth, connectors |
| `ruff` / `black` / `mypy` | clean across `app` and `tests` (219 source files) |
| Migration | `0023_user_profile_timeline` applied; `user_profiles` RLS policy verified in psql |
| Frontend | `tsc --noEmit` clean · `eslint src` clean · `next build` succeeded (6 routes) |
| Live stack | Real turn through Postgres + Ollama: fact stated in chat → auto-extracted to memory → recalled in a *new* conversation |
| Cloud SDKs | `sentry-sdk` and `posthog` uninstalled; the app boots and the suite passes without them |

---

## 9. Where this stops, and what is next

**Done and working:** local stack, local auth + Google OAuth, instant recall,
consolidation, learned profile, episodic timeline, emotional tone, calendar
import, one-interface web client.

**Next, in order of value:**

1. **Gmail + Drive connectors** — needs a `connector_credentials` table (stored
   refresh tokens, incremental scopes, per-connector revocation) plus a background
   sync worker. The `Signal` seam and `ingest()` already exist, so this is
   credentials and scheduling, not new memory machinery.
2. **Workflow learning (the original M9)** — detect recurring request shapes and
   offer to run them, under the existing Green/Yellow/Red approval model.
3. **Semantic consolidation pass** — merge facts that are equal in meaning but
   not in wording ("Works at Acme" / "Employed by Acme Corp"). Belongs in the
   background worker, since it needs embeddings.
4. **Vector file RAG** — file retrieval is still keyword-based.
5. **Live web search** — provider seam exists (Brave/Tavily), unkeyed.
6. **Timeline UI** — the read path and the prompt block exist; there is no panel
   that shows the user their own week yet.
