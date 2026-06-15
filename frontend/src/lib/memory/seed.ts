/**
 * Seed memories — a believable starter set so the Memory Experience feels alive
 * on first run. Persisted to local storage on first load (see `store.ts`); the
 * user can edit, archive, or delete from there.
 *
 * When the backend memory API lands, this seed is replaced by the live fetch
 * (the store is the single swap point) — see `lib/api/resources.ts`.
 */

import type { Memory } from "@/lib/memory/types";

export const SEED_MEMORIES: Memory[] = [
  {
    id: "mem-qualcomm-2026",
    content: "Applied to Qualcomm for a 2026 hardware engineering role.",
    category: "career",
    importance: "high",
    source: "conversation",
    status: "active",
    created_at: "2026-01-12T09:30:00.000Z",
    updated_at: "2026-01-12T09:30:00.000Z",
    versions: [],
  },
  {
    id: "mem-concise-answers",
    content: "Prefers concise, direct answers without filler.",
    category: "preferences",
    importance: "critical",
    source: "manual",
    status: "active",
    created_at: "2026-02-02T14:10:00.000Z",
    updated_at: "2026-05-28T08:05:00.000Z",
    versions: [
      {
        content: "Prefers shorter answers.",
        changed_at: "2026-05-28T08:05:00.000Z",
      },
    ],
  },
  {
    id: "mem-gummy-os",
    content:
      "Building GUMMY, a personal AI operating system, as the flagship project.",
    category: "projects",
    importance: "critical",
    source: "conversation",
    status: "active",
    created_at: "2026-03-18T11:45:00.000Z",
    updated_at: "2026-06-10T19:20:00.000Z",
    versions: [],
  },
  {
    id: "mem-learning-rag",
    content:
      "Learning retrieval-augmented generation and vector search for the memory layer.",
    category: "learning",
    importance: "medium",
    source: "conversation",
    status: "active",
    created_at: "2026-04-05T16:00:00.000Z",
    updated_at: "2026-04-05T16:00:00.000Z",
    versions: [],
  },
  {
    id: "mem-goal-ship-mvp",
    content: "Wants to ship the GUMMY web MVP before the end of summer 2026.",
    category: "goals",
    importance: "high",
    source: "conversation",
    status: "active",
    created_at: "2026-04-20T10:15:00.000Z",
    updated_at: "2026-06-01T07:40:00.000Z",
    versions: [],
  },
  {
    id: "mem-timezone",
    content: "Based in Kuala Lumpur (GMT+8); prefers mornings for deep work.",
    category: "personal",
    importance: "medium",
    source: "manual",
    status: "active",
    created_at: "2026-04-22T22:05:00.000Z",
    updated_at: "2026-04-22T22:05:00.000Z",
    versions: [],
  },
  {
    id: "mem-design-identity",
    content:
      "Cares deeply about a premium, glassy visual identity with the living orb motif.",
    category: "preferences",
    importance: "high",
    source: "conversation",
    status: "active",
    created_at: "2026-05-03T13:25:00.000Z",
    updated_at: "2026-05-03T13:25:00.000Z",
    versions: [],
  },
  {
    id: "mem-business-solo",
    content:
      "Running GUMMY as a solo founder; budget-conscious about infrastructure.",
    category: "business",
    importance: "medium",
    source: "conversation",
    status: "active",
    created_at: "2026-05-15T18:50:00.000Z",
    updated_at: "2026-05-15T18:50:00.000Z",
    versions: [],
  },
  {
    id: "mem-stack",
    content:
      "Stack is Next.js 16 + FastAPI + Supabase; ships in tagged milestones.",
    category: "projects",
    importance: "medium",
    source: "agent",
    status: "active",
    created_at: "2026-05-30T12:00:00.000Z",
    updated_at: "2026-05-30T12:00:00.000Z",
    versions: [],
  },
  {
    id: "mem-old-role",
    content: "Previously explored a startup idea around fitness tracking.",
    category: "career",
    importance: "low",
    source: "conversation",
    status: "archived",
    created_at: "2026-02-28T09:00:00.000Z",
    updated_at: "2026-03-10T09:00:00.000Z",
    versions: [],
  },
];
