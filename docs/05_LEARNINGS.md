# 05 — Learnings

Durable lessons from building GUMMY, organized by area. These are the things
worth remembering for M5 and beyond.

## Frontend

- **One source of truth for server state.** Routing memories, conversations,
  messages, and search through TanStack Query keys (and invalidating on mutation)
  eliminated an entire class of stale-UI bugs. Local stores that mirror server
  data drift; delete them.
- **Streaming UIs need a lifecycle, not just a happy path.** Cancellation
  (unmount + navigation), failure fallback, and duplicate suppression are part of
  the feature, not polish.
- **Touch-first beats hover.** Hover-revealed controls vanish on phones. Always
  provide a visible affordance and ≥44px targets on mobile; use `sm:`/`lg:` to
  shrink for pointer devices.
- **16px inputs on mobile** prevent iOS Safari zoom-on-focus — a tiny detail that
  makes the app feel native.
- **Reduced motion is cheap insurance.** A global `prefers-reduced-motion` rule
  plus `useReducedMotion` in the animated components covers accessibility without
  per-component bespoke work.

## Backend

- **Thin routers, fat services, pure repositories.** Keeping query construction in
  pure functions made the full-text/pgvector SQL **unit-testable without a
  database** by compiling against the PostgreSQL dialect.
- **Route ordering matters.** Literal paths (`/message-search`) must be registered
  before parametrized ones (`/{conversation_id}`) or they get swallowed.
- **Idempotency is a feature.** Embedding by content hash + model name means
  re-runs are free and safe — essential for workers and re-embedding.

## Memory

- **Recall is ranking over everything, not lookup within a thread.** Cross-
  conversation memory only works because retrieval ranks the whole corpus.
- **Provenance and versioning pay off.** Tracking a memory's source and edit
  history turns “the AI said something weird” into a debuggable trail.
- **Expose content, never internals.** Embeddings and scores stay server-side.

## Database

- **Enforce tenancy in the database (RLS), not just the app.** A missing
  `WHERE user_id` should fail safe, not leak. RLS is the backstop.
- **Migrate incrementally.** 18 small migrations (soft delete, embeddings, RLS,
  summaries, sources, watermark, …) are far easier to reason about and reverse
  than monolithic schema changes.

## Streaming

- **SSE is enough.** A simple `data:`-framed event stream with `delta` then a
  terminal `done` (carrying persisted ids + memories used) is robust and easy to
  parse — no websockets required.
- **Swap live text for persisted text by invalidating *before* clearing** the live
  bubble, so there's no flicker and no duplicate message.

## Architecture

- **Contract-first.** Pydantic schemas and hand-typed client resources kept the
  frontend and backend honest across milestones.
- **Scaffold the future, gate the present.** The agent framework exists in the
  codebase but is intentionally not exposed in M4 — build the runway without
  shipping half-built runways to users.

## Product

- **Trust is the product.** A visible, editable, searchable memory store is what
  makes a “remembering” assistant feel safe instead of creepy.
- **Don't show the roadmap as if it shipped.** Placeholders and “Soon” badges
  erode trust with the exact audience (users, recruiters) you're trying to win.
- **Polish compounds.** Touch targets, no-flicker streaming, reduced motion, and
  honest empty states are individually small and collectively the difference
  between “demo” and “product.”
