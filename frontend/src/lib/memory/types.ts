/**
 * Memory domain types — the shape the Memory Experience (M4) renders against.
 *
 * Today these are backed by a local, persisted store (see `store.ts`) seeded
 * with demo memories so the experience is fully usable without the backend.
 * The same types map cleanly onto the backend `MemoryItem` (Phase 1–3 schema),
 * so swapping the store for live API calls is a drop-in change — see
 * `fromApi`/`toApi` adapters below.
 */

import {
  importanceFromScore,
  type MemoryCategory,
  type MemoryImportance,
  type MemorySource,
  getImportanceMeta,
} from "@/config/memory";
import type { MemoryItem } from "@/lib/api/resources";

export type MemoryStatus = "active" | "archived";

/** The editable fields of a memory (create + edit form payload). */
export interface MemoryDraft {
  content: string;
  category: MemoryCategory;
  importance: MemoryImportance;
}

/** A single prior revision of a memory's content (version history). */
export interface MemoryVersion {
  content: string;
  /** ISO timestamp this revision was replaced. */
  changed_at: string;
}

export interface Memory {
  id: string;
  content: string;
  category: MemoryCategory;
  importance: MemoryImportance;
  source: MemorySource;
  status: MemoryStatus;
  /** ISO timestamps. */
  created_at: string;
  updated_at: string;
  /** Prior revisions, newest last. Empty until the memory is edited. */
  versions: MemoryVersion[];
}

/** Sort options for the timeline (Deliverable 8). */
export type MemorySort = "newest" | "oldest" | "updated";

/**
 * Query envelope for listing memories.
 *
 * Phase 5 seam: `query` is keyword search today. Fields are intentionally
 * shaped to grow into hybrid search / metadata filtering / query transformation
 * / re-ranking without changing call sites — see `query.ts`.
 */
export interface MemoryQuery {
  /** Free-text search across content + category. */
  query?: string;
  /** Restrict to a single category, or "all". */
  category?: MemoryCategory | "all";
  /** Restrict to a status; defaults to "active". */
  status?: MemoryStatus | "all";
  sort?: MemorySort;
}

/** Aggregate stats for the transparency + header surfaces. */
export interface MemoryStats {
  total: number;
  active: number;
  archived: number;
  byCategory: Record<string, number>;
  byImportance: Record<MemoryImportance, number>;
  lastUpdated: string | null;
}

// ── Backend adapters (extension point) ────────────────────────────────────────

/** Map a backend MemoryItem onto the richer UI Memory model. */
export function fromApi(item: MemoryItem): Memory {
  return {
    id: item.id,
    content: item.content,
    category: item.category as MemoryCategory,
    importance: importanceFromScore(item.importance_score),
    source: "conversation",
    status: item.status === "archived" ? "archived" : "active",
    created_at: item.created_at,
    updated_at: item.updated_at,
    versions: [],
  };
}

/** Map a UI Memory back onto the backend write shape (importance → score). */
export function toApi(
  memory: Memory,
): Pick<
  MemoryItem,
  "category" | "content" | "importance_score" | "status"
> {
  return {
    category: memory.category,
    content: memory.content,
    importance_score: getImportanceMeta(memory.importance).score,
    status: memory.status,
  };
}
