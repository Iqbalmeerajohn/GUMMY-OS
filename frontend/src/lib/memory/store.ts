/**
 * Memory store — local, persisted source of truth for the Memory Experience.
 *
 * This is the single swap point for the backend: every read/write goes through
 * here, so wiring the live API (see `lib/api/resources.ts` + `types.ts`
 * adapters) means replacing these actions, not the UI.
 *
 * Persisted to localStorage so memories survive reloads. Components read it via
 * the hooks in `useMemory.ts` behind a hydration guard to avoid SSR mismatch.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { MemoryCategory, MemoryImportance } from "@/config/memory";
import { SEED_MEMORIES } from "@/lib/memory/seed";
import type { Memory } from "@/lib/memory/types";

export interface MemoryDraft {
  content: string;
  category: MemoryCategory;
  importance: MemoryImportance;
}

interface MemoryState {
  memories: Memory[];
  add: (draft: MemoryDraft) => Memory;
  update: (id: string, patch: Partial<MemoryDraft>) => void;
  archive: (id: string) => void;
  restore: (id: string) => void;
  remove: (id: string) => void;
  /** Reset to the seed set (used by the empty-state "restore demo" affordance). */
  reset: () => void;
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `mem-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export const useMemoryStore = create<MemoryState>()(
  persist(
    (set, get) => ({
      memories: SEED_MEMORIES,

      add: (draft) => {
        const now = new Date().toISOString();
        const memory: Memory = {
          id: newId(),
          content: draft.content.trim(),
          category: draft.category,
          importance: draft.importance,
          source: "manual",
          status: "active",
          created_at: now,
          updated_at: now,
          versions: [],
        };
        set({ memories: [memory, ...get().memories] });
        return memory;
      },

      update: (id, patch) =>
        set({
          memories: get().memories.map((m) => {
            if (m.id !== id) return m;
            const now = new Date().toISOString();
            const contentChanged =
              patch.content !== undefined &&
              patch.content.trim() !== m.content;
            return {
              ...m,
              content:
                patch.content !== undefined
                  ? patch.content.trim()
                  : m.content,
              category: patch.category ?? m.category,
              importance: patch.importance ?? m.importance,
              updated_at: now,
              // Version history: snapshot the prior content on a content change.
              versions: contentChanged
                ? [...m.versions, { content: m.content, changed_at: now }]
                : m.versions,
            };
          }),
        }),

      archive: (id) =>
        set({
          memories: get().memories.map((m) =>
            m.id === id
              ? { ...m, status: "archived", updated_at: new Date().toISOString() }
              : m,
          ),
        }),

      restore: (id) =>
        set({
          memories: get().memories.map((m) =>
            m.id === id
              ? { ...m, status: "active", updated_at: new Date().toISOString() }
              : m,
          ),
        }),

      remove: (id) =>
        set({ memories: get().memories.filter((m) => m.id !== id) }),

      reset: () => set({ memories: SEED_MEMORIES }),
    }),
    {
      name: "gummy.memories.v1",
      version: 1,
    },
  ),
);
