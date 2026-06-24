# 06 — Release Notes: M4

**Milestone:** M4 — Memory Experience, Workspace, and Final Stabilization
**Status:** Feature-complete and stabilized for early real-user testing.

M4 turns GUMMY from a memory backend into a usable, polished product: a streaming
chat workspace, a first-class Memory Center, full conversation management, unified
search, and a mobile-ready, accessible UI.

## Features

- **Workspace chat** with token **streaming** (SSE), agent-context selector, auto-
  scroll that respects manual scroll-up, and a welcome screen (quick actions +
  memory snapshot).
- **Memory system**: automatic extraction, embedding, semantic retrieval, and
  **cross-conversation recall** surfaced as a “Memory Used” disclosure (content
  only — never embeddings/scores).
- **Memory Center**: create, edit, archive/restore, delete, category filters,
  sorting, and search; source tracking via `memory_sources`.
- **Conversation management**: create, rename, delete (with confirm), pin/unpin,
  archive/restore, pinned section, and a searchable history rail.
- **Unified search** (new): a `/search` page querying **conversations, messages,
  and memories** in parallel, with grouped + highlighted results, keyboard
  navigation, deep-linking into the workspace, and loading/empty states. Reachable
  from a header search button on every screen.
- **Profile & settings**: editable display name, timezone, language; account info;
  recent activity.
- **Dashboard, Updates, Future Vision** surfaces with proper empty/loading states.

## Improvements

- **Streaming resilience**: `AbortController` cancellation on unmount and on
  conversation switch, silent handling of intentional aborts, mounted-ref guards
  against setState-after-unmount, and **fallback to the non-streaming endpoint**
  when a stream breaks.
- **Mobile UX**: conversation actions menu always visible on touch; ≥44px touch
  targets across the history rail, conversation menu, and composer; 16px composer
  text to prevent iOS zoom-on-focus.
- **Accessibility**: global `prefers-reduced-motion` handling plus reduced-motion
  in animated components; safe match highlighting (no `dangerouslySetInnerHTML`);
  focus-visible states; ARIA labels on icon controls.
- **Honest UI**: removed all “Planned”/placeholder controls from profile, settings,
  and the conversation menu — only working functionality is shown.

## Bug fixes

- Demo memory seed/store removed; the Memory Experience now reflects the database
  only.
- Removed dead code (`useSendTurn`; repurposed `postTurn` as the streaming fallback).
- Search no longer limited to client-side conversation-title filtering.
- Conversation streaming no longer bleeds a reply into another thread on switch.

## Performance

- **Memory retrieval** is a single tenant-scoped pgvector ranking query (no
  per-row round-trips).
- **Unified search** runs its three queries in parallel and debounces input
  (~220ms) so typing feels instant.
- **Server state** is deduped through TanStack Query keys; conversation switching
  reads cached messages.
- Known follow-up: a minor N+1 in `conversation_search_service` (per-hit
  conversation re-fetch) — batch before scale.

## Verification

- Backend: **355 tests passing**, 4 Postgres-only skipped (includes new
  message-search builder tests). `ruff` clean.
- Frontend: `tsc --noEmit` clean, `eslint` clean.

## Explicitly out of scope (M4)

- No new user-facing agents (the agent framework remains scaffolded, not enabled).
- No multimodal attachments / voice (composer seams are inert by design).
- No speculative features.
