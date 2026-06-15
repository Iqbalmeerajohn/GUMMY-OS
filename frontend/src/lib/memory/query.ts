/**
 * Memory querying — filter, search, and sort, kept as pure functions so they're
 * trivial to test and reuse across surfaces.
 *
 * ── Phase 5 extension points ──────────────────────────────────────────────────
 * The current `searchMemories` is a keyword matcher. It is deliberately the only
 * place ranking/matching happens, so Phase 5 can grow it without touching call
 * sites:
 *   • Hybrid search        → blend this keyword score with a vector similarity score.
 *   • Query transformation → expand/rewrite `q.query` before matching.
 *   • Metadata filtering    → richer predicates over category/importance/source/date.
 *   • Re-ranking            → reorder the keyword/vector candidate set.
 *   • Context construction  → select a token-budgeted subset for prompt assembly.
 * Each is marked inline below.
 */

import { importanceWeight } from "@/config/memory";
import type { Memory, MemoryQuery, MemoryStats } from "@/lib/memory/types";

function matchesText(memory: Memory, term: string): boolean {
  if (!term) return true;
  const haystack = `${memory.content} ${memory.category}`.toLowerCase();
  // Phase 5 seam: replace substring match with hybrid keyword + vector scoring.
  return term
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((token) => haystack.includes(token));
}

function compare(a: Memory, b: Memory, sort: MemoryQuery["sort"]): number {
  switch (sort) {
    case "oldest":
      return a.created_at.localeCompare(b.created_at);
    case "updated":
      return b.updated_at.localeCompare(a.updated_at);
    case "newest":
    default:
      return b.created_at.localeCompare(a.created_at);
  }
}

/** Filter + search + sort a memory list per the query envelope. */
export function searchMemories(
  memories: Memory[],
  q: MemoryQuery = {},
): Memory[] {
  const status = q.status ?? "active";
  const category = q.category ?? "all";
  const term = (q.query ?? "").trim();

  // Phase 5 seam (metadata filtering): expand these predicates.
  const filtered = memories.filter((m) => {
    if (status !== "all" && m.status !== status) return false;
    if (category !== "all" && m.category !== category) return false;
    if (!matchesText(m, term)) return false;
    return true;
  });

  // Phase 5 seam (re-ranking): this stable sort is the candidate ordering.
  return filtered.sort((a, b) => compare(a, b, q.sort));
}

/** The most important active memories first (importance, then recency). */
export function topMemories(memories: Memory[], limit = 5): Memory[] {
  return memories
    .filter((m) => m.status === "active")
    .sort((a, b) => {
      const w = importanceWeight(b.importance) - importanceWeight(a.importance);
      return w !== 0 ? w : b.updated_at.localeCompare(a.updated_at);
    })
    .slice(0, limit);
}

/** Aggregate counts for header + transparency surfaces. */
export function computeStats(memories: Memory[]): MemoryStats {
  const stats: MemoryStats = {
    total: memories.length,
    active: 0,
    archived: 0,
    byCategory: {},
    byImportance: { low: 0, medium: 0, high: 0, critical: 0 },
    lastUpdated: null,
  };

  for (const m of memories) {
    if (m.status === "archived") stats.archived += 1;
    else stats.active += 1;
    stats.byCategory[m.category] = (stats.byCategory[m.category] ?? 0) + 1;
    stats.byImportance[m.importance] += 1;
    if (!stats.lastUpdated || m.updated_at > stats.lastUpdated) {
      stats.lastUpdated = m.updated_at;
    }
  }

  return stats;
}
