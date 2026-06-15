"use client";

import { useMemo, useSyncExternalStore } from "react";

import { useMemoryStore } from "@/lib/memory/store";
import {
  computeStats,
  searchMemories,
  topMemories,
} from "@/lib/memory/query";
import { buildTransparency } from "@/lib/memory/transparency";
import type { Memory, MemoryQuery } from "@/lib/memory/types";

const noopSubscribe = () => () => {};

/**
 * True once the client has mounted. Persisted (localStorage) state can differ
 * from the server-rendered seed, so store-derived UI gates on this to avoid
 * hydration mismatch — render skeletons until ready. Uses useSyncExternalStore
 * so the server snapshot is always `false` (no setState-in-effect).
 */
export function useMemoriesReady(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
}

/** Filtered + sorted memory list per the query envelope. */
export function useMemoryList(query: MemoryQuery): Memory[] {
  const memories = useMemoryStore((s) => s.memories);
  return useMemo(() => searchMemories(memories, query), [memories, query]);
}

/** A single memory by id (or undefined). */
export function useMemory(id: string | null): Memory | undefined {
  const memories = useMemoryStore((s) => s.memories);
  return useMemo(
    () => (id ? memories.find((m) => m.id === id) : undefined),
    [memories, id],
  );
}

/** Aggregate counts for headers + transparency. */
export function useMemoryStats() {
  const memories = useMemoryStore((s) => s.memories);
  return useMemo(() => computeStats(memories), [memories]);
}

/** "What GUMMY knows about you" grouped summary. */
export function useTransparency() {
  const memories = useMemoryStore((s) => s.memories);
  return useMemo(() => buildTransparency(memories), [memories]);
}

/** Most important active memories (dashboard widget + workspace hub). */
export function useTopMemories(limit = 5): Memory[] {
  const memories = useMemoryStore((s) => s.memories);
  return useMemo(() => topMemories(memories, limit), [memories, limit]);
}

/** Write actions, stable across renders (actions never change identity). */
export function useMemoryActions() {
  const add = useMemoryStore((s) => s.add);
  const update = useMemoryStore((s) => s.update);
  const archive = useMemoryStore((s) => s.archive);
  const restore = useMemoryStore((s) => s.restore);
  const remove = useMemoryStore((s) => s.remove);
  const reset = useMemoryStore((s) => s.reset);
  return useMemo(
    () => ({ add, update, archive, restore, remove, reset }),
    [add, update, archive, restore, remove, reset],
  );
}
