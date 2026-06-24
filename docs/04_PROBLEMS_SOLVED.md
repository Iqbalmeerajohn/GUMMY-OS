# 04 — Problems Solved

A log of the significant issues resolved while building GUMMY, with root cause,
fix, files touched, and the lesson taken forward. Entries marked **(M4 stabilization)**
were fixed in the final M4 hardening pass.

---

## 1. Memory not persisting (demo store shadowing the database)

- **Problem:** The Memory Experience showed seeded/demo data and edits didn't
  durably persist.
- **Root cause:** A local seed + client store (`lib/memory/seed.ts`,
  `lib/memory/store.ts`) backed the UI in early milestones and was never removed,
  so the UI reflected in-memory demo state instead of the backend.
- **Fix:** Deleted the demo seed/store; `useMemory` now reads a single
  TanStack Query (`["memories","all"]`) backed by the real API, and all writes
  invalidate that key.
- **Files:** `lib/memory/useMemory.ts`, removed `lib/memory/seed.ts`,
  `lib/memory/store.ts`.
- **Lesson:** Delete scaffolding the moment the real source lands; a “temporary”
  store becomes a silent source of truth.

## 2. Memory not retrieving across conversations

- **Problem:** Facts learned in one conversation didn't surface in others.
- **Root cause:** Retrieval needs embeddings ranked over the *whole* user corpus,
  not the current thread; this requires pgvector and tenant-scoped ranking.
- **Fix:** `search_repository` ranks `memories ⋈ memory_embeddings` by cosine
  distance, tenant-scoped and live-only; the turn service embeds each query,
  retrieves top memories, and injects them into context.
- **Files:** `repositories/search_repository.py`,
  `services/conversation/conversation_turn_service.py`.
- **Lesson:** “Recall” is a ranking problem over all data, not a per-thread lookup.

## 3. RLS worker issue (background jobs and tenant policies)

- **Problem:** Background workers query the same RLS-protected tables as the
  request path, but have no JWT/session user to scope to.
- **Root cause:** RLS policies depend on a tenant context that the request path
  derives from the bearer token; workers run outside that context.
- **Fix:** Workers set an explicit tenant context (`core/tenant_context.py`) before
  querying, so embedding/enrichment jobs observe the same policies as requests.
- **Files:** `core/tenant_context.py`, `workers/embedding_worker.py`,
  `workers/enrichment_worker.py`.
- **Lesson:** Security boundaries must hold on *every* code path — request,
  worker, and migration — not just the obvious one.

## 4. Conversation title generation

- **Problem:** New conversations needed meaningful titles without blocking the
  first reply.
- **Root cause:** Titles depend on the first exchange, which isn't known at
  creation time (conversations are created lazily on first message).
- **Fix:** Title generation is handled in the turn service and surfaced via the
  conversation record; the history rail shows “New” until a title exists.
- **Files:** `services/conversation/conversation_turn_service.py`,
  `services/conversation/conversation_service.py`.
- **Lesson:** Derive display data from the first real signal; don't force it at
  creation.

## 5. “Blank workspace” bug (eager conversation creation)

- **Problem:** Starting a new chat intermittently showed a blank pane instead of
  the welcome screen.
- **Root cause:** Creating the conversation eagerly set `activeId`, which
  suppressed the welcome state and left an empty thread.
- **Fix:** Conversations are now created **lazily** on the first message; “New”
  simply resets `activeId` to `null` and shows the welcome screen.
- **Files:** `app/workspace/page.tsx`, `components/workspace/ChatPane.tsx`.
- **Lesson:** Don't allocate server state until the user commits to it.

## 6. Streaming fragility — leaks, bleed, dead ends **(M4 stabilization)**

- **Problem:** The SSE stream had no cancellation: switching conversations mid-
  stream bled a half-finished reply into another thread, unmounting leaked the
  reader (setState-after-unmount), and a broken stream was a dead end.
- **Root cause:** `streamTurn` accepted an `AbortSignal` but `ChatPane` never
  created or passed one, and had no fallback path.
- **Fix:** `ChatPane` now owns an `AbortController`: aborts on unmount and on
  switching to a *different* conversation (while excluding the “promote a new
  chat” case via a streaming-conversation ref), stays silent on intentional
  aborts, guards state writes with a mounted ref, and **falls back to the
  non-streaming turn endpoint** if the stream breaks mid-flight.
- **Files:** `components/workspace/ChatPane.tsx`, `lib/api/resources.ts`.
- **Lesson:** A streaming UI isn't done until cancellation, unmount, and failure
  are all handled.

## 7. Profile exposed unbuilt features **(M4 stabilization)**

- **Problem:** Profile/settings showed “Planned” placeholders — fake profile-
  picture upload, fake theme toggle, a “Future Capabilities” list, and a “Move to
  Workspace — Soon” menu row.
- **Root cause:** Roadmap UI shipped ahead of functionality.
- **Fix:** Removed every non-functional placeholder; the surfaces now show only
  real, working controls.
- **Files:** `app/(app)/profile/page.tsx`, `app/(app)/settings/profile/page.tsx`,
  `components/workspace/ConversationMenu.tsx`.
- **Lesson:** Never ship dead UI to real users; a “Soon” badge is a bug report.

## 8. Search was incomplete **(M4 stabilization)**

- **Problem:** “Search” only filtered the ~30 loaded conversation titles client-
  side. Message content and memories were unsearchable despite capable backends.
- **Root cause:** The frontend never called the existing `/conversations/search`
  or `/memories/search` endpoints, and no message-level search endpoint existed.
- **Fix:** Added a message full-text search endpoint, then built a unified
  `/search` page that queries conversations, messages, and memories in parallel
  with grouped, highlighted results, keyboard navigation, and loading/empty states.
- **Files:** `repositories/conversation_search_repository.py`,
  `schemas/search.py`, `api/v1/conversations.py`, `app/(app)/search/page.tsx`,
  `lib/api/resources.ts`, `components/app/AppHeader.tsx`.
- **Lesson:** Capability on the backend is worthless until a path reaches the user.

## 9. Mobile 3-dot menu invisible **(M4 stabilization)**

- **Problem:** The conversation actions menu was `opacity-0` + hover-only, so it
  was unusable on touch devices, and touch targets were below 44px.
- **Root cause:** Desktop hover affordance with no touch fallback.
- **Fix:** The menu icon is always visible on mobile (hover-revealed on desktop),
  with ≥44px touch targets on the trigger, menu rows, and composer controls; the
  message textarea uses 16px text on mobile to stop iOS zoom-on-focus.
- **Files:** `components/workspace/HistoryRail.tsx`,
  `components/workspace/ConversationMenu.tsx`, `components/workspace/Composer.tsx`.
- **Lesson:** Hover is not an interaction model on phones; design touch-first.
