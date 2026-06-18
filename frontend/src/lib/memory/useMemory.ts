"use client";

import { useMemo } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/auth/AuthProvider";
import { getImportanceMeta } from "@/config/memory";
import {
  archiveMemory,
  createMemory,
  deleteMemory,
  fetchMemories,
  restoreMemory,
  updateMemory,
} from "@/lib/api/resources";
import {
  computeStats,
  searchMemories,
  topMemories,
} from "@/lib/memory/query";
import { buildTransparency } from "@/lib/memory/transparency";
import { fromApi, type MemoryDraft } from "@/lib/memory/types";
import type { Memory, MemoryQuery } from "@/lib/memory/types";

const MEMORIES_KEY = ["memories", "all"] as const;

/**
 * Single source of truth: the user's memories from the backend. Every memory
 * hook reads this one query (deduped by key), so the local demo store is gone —
 * the Memory Experience now reflects the database only.
 */
function useMemoriesQuery() {
  const { user } = useAuth();
  return useQuery({
    queryKey: MEMORIES_KEY,
    queryFn: async (): Promise<Memory[]> => {
      // No status filter → active + archived, so the Center can toggle both
      // and compute accurate stats. 100 is the API's max page size.
      const page = await fetchMemories({ limit: 100 });
      return page.items.map(fromApi);
    },
    enabled: !!user,
    retry: false,
  });
}

function useMemories(): Memory[] {
  return useMemoriesQuery().data ?? [];
}

/**
 * True once the memories query has resolved (success or error). Store-derived
 * UI gates on this to render skeletons until the first fetch completes.
 */
export function useMemoriesReady(): boolean {
  const { isLoading } = useMemoriesQuery();
  return !isLoading;
}

/** Filtered + sorted memory list per the query envelope. */
export function useMemoryList(query: MemoryQuery): Memory[] {
  const memories = useMemories();
  return useMemo(() => searchMemories(memories, query), [memories, query]);
}

/** A single memory by id (or undefined). */
export function useMemory(id: string | null): Memory | undefined {
  const memories = useMemories();
  return useMemo(
    () => (id ? memories.find((m) => m.id === id) : undefined),
    [memories, id],
  );
}

/** Aggregate counts for headers + transparency. */
export function useMemoryStats() {
  const memories = useMemories();
  return useMemo(() => computeStats(memories), [memories]);
}

/** "What GUMMY knows about you" grouped summary. */
export function useTransparency() {
  const memories = useMemories();
  return useMemo(() => buildTransparency(memories), [memories]);
}

/** Most important active memories (dashboard widget + workspace hub). */
export function useTopMemories(limit = 5): Memory[] {
  const memories = useMemories();
  return useMemo(() => topMemories(memories, limit), [memories, limit]);
}

// Snapshot ranking: personal facts first, then preferences, projects, career,
// learning — so the welcome snapshot surfaces identity-defining memories rather
// than incidental ones.
const SNAPSHOT_PRIORITY: Record<string, number> = {
  profile: 0,
  preference: 1,
  project: 2,
  career: 3,
  learning: 4,
  conversation: 5,
  document: 6,
};

/** Top memories for the welcome snapshot, ranked by category then importance. */
export function useSnapshotMemories(limit = 3): Memory[] {
  const memories = useMemories();
  return useMemo(() => {
    const importanceRank: Record<string, number> = {
      critical: 0,
      high: 1,
      medium: 2,
      low: 3,
    };
    return memories
      .filter((m) => m.status === "active")
      .sort((a, b) => {
        const cat =
          (SNAPSHOT_PRIORITY[a.category] ?? 9) -
          (SNAPSHOT_PRIORITY[b.category] ?? 9);
        if (cat !== 0) return cat;
        const imp = importanceRank[a.importance] - importanceRank[b.importance];
        if (imp !== 0) return imp;
        return b.updated_at.localeCompare(a.updated_at);
      })
      .slice(0, limit);
  }, [memories, limit]);
}

function draftToWrite(draft: MemoryDraft) {
  return {
    category: draft.category,
    content: draft.content,
    importance_score: getImportanceMeta(draft.importance).score,
  };
}

/** Write actions, backed by the backend API and stable across renders. */
export function useMemoryActions() {
  const qc = useQueryClient();
  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["memories"] });
  const onError = (err: unknown) =>
    toast.error(err instanceof Error ? err.message : "Something went wrong.");

  const add = useMutation({
    mutationFn: (draft: MemoryDraft) => createMemory(draftToWrite(draft)),
    onSuccess: invalidate,
    onError,
  });
  const update = useMutation({
    mutationFn: ({ id, draft }: { id: string; draft: Partial<MemoryDraft> }) =>
      updateMemory(id, {
        content: draft.content,
        category: draft.category,
        importance_score:
          draft.importance !== undefined
            ? getImportanceMeta(draft.importance).score
            : undefined,
      }),
    onSuccess: invalidate,
    onError,
  });
  const archive = useMutation({
    mutationFn: (id: string) => archiveMemory(id),
    onSuccess: invalidate,
    onError,
  });
  const restore = useMutation({
    mutationFn: (id: string) => restoreMemory(id),
    onSuccess: invalidate,
    onError,
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteMemory(id),
    onSuccess: invalidate,
    onError,
  });

  return useMemo(
    () => ({
      add: (draft: MemoryDraft) => add.mutate(draft),
      update: (id: string, draft: Partial<MemoryDraft>) =>
        update.mutate({ id, draft }),
      archive: (id: string) => archive.mutate(id),
      restore: (id: string) => restore.mutate(id),
      remove: (id: string) => remove.mutate(id),
    }),
    [add, update, archive, restore, remove],
  );
}
