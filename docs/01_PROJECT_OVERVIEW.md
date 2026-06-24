# 01 — Project Overview

## What GUMMY OS is

GUMMY OS is a personal, memory-first AI operating layer. At its center is **Gummy**,
an assistant that learns the user through conversation and remembers what matters
across sessions — securely, with consent, and under the user's control.

The product today (milestone **M4**) is a polished single-user web app: a
workspace where you converse with Gummy, a long-term **Memory** system that
extracts and recalls facts across conversations, full **conversation management**,
**unified search**, and a dashboard/profile surface. The longer roadmap extends
this into a coordinated multi-agent system, but **M4 is deliberately scoped to a
stable, shippable memory-and-chat core**.

## Goals

- **Memory that persists and recalls.** Gummy should remember identity-defining
  facts and surface them in future, unrelated conversations.
- **Trust and transparency.** The user can see, search, edit, archive, and delete
  everything Gummy remembers. Embeddings and scores are never exposed in the UI.
- **Premium, fast, native-feeling UX** on desktop and mobile.
- **Production-grade foundations** — tenant isolation (RLS), typed contracts,
  tested services — so the multi-agent roadmap can be built on solid ground.

## Architecture at a glance

```
┌────────────────────────────┐        ┌──────────────────────────────┐
│  Frontend (Next.js 16)     │  HTTPS │  Backend (FastAPI)           │
│  App Router · React 19     │ ─────► │  Async SQLAlchemy · Pydantic │
│  TanStack Query · Tailwind │  SSE   │  Services / Repositories     │
│  framer-motion · three     │ ◄───── │  Streaming turn endpoint     │
└────────────────────────────┘        └───────────────┬──────────────┘
                                                       │
                                  ┌────────────────────┼─────────────────────┐
                                  │                     │                     │
                          PostgreSQL + pgvector   Background workers     Supabase Auth
                          (RLS tenant isolation)  (embeddings,           (JWT bearer)
                                                   enrichment)
```

## Tech stack

**Frontend**
- Next.js 16 (App Router) · React 19 · TypeScript
- TanStack Query (server state) · Zustand (light UI state)
- Tailwind CSS v4 · framer-motion · three / @react-three/fiber (the living orb)
- Supabase SSR auth client · sonner (toasts)

**Backend**
- FastAPI · async SQLAlchemy 2.x · Pydantic v2
- PostgreSQL + **pgvector** (semantic search) · Alembic (18 migrations)
- Supabase-issued JWT verification · Row-Level Security for tenant isolation
- Background workers for embedding + enrichment
- pytest (355 passing / 4 Postgres-only skipped)

## Current capabilities (M4)

- **Workspace chat** with token streaming (SSE), agent-context routing, and a
  welcome screen with quick actions and a memory snapshot.
- **Memory system**: automatic extraction from conversation, embedding,
  semantic retrieval, and cross-conversation recall surfaced as “Memory Used”.
- **Memory Center**: full CRUD, archive/restore, category filters, sorting, and
  search over everything Gummy remembers.
- **Conversation management**: create, rename, delete, pin/unpin, archive/restore,
  and a searchable history rail.
- **Unified search** across conversations, messages, and memories.
- **Profile & settings**: real, editable identity (display name, timezone,
  language) with recent activity.
- **Dashboard, Updates, Future Vision** surfaces.
- **Mobile-first** layouts with reduced-motion support throughout.

See [02_ARCHITECTURE.md](02_ARCHITECTURE.md) and [03_MEMORY_SYSTEM.md](03_MEMORY_SYSTEM.md)
for depth, and [06_RELEASE_NOTES_M4.md](06_RELEASE_NOTES_M4.md) for the M4 changelog.
