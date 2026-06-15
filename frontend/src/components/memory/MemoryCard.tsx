"use client";

import { Clock } from "lucide-react";

import { CategoryChip, ImportanceBadge } from "@/components/memory/MemoryBadges";
import { getSourceLabel } from "@/config/memory";
import { formatMonthYear } from "@/lib/format";
import type { Memory } from "@/lib/memory/types";

/** A single memory in the list/grid (Deliverable 2). Click to open detail. */
export function MemoryCard({
  memory,
  onOpen,
}: {
  memory: Memory;
  onOpen: (id: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(memory.id)}
      className="glass elevation-2 hover:border-primary/40 flex h-full w-full flex-col rounded-2xl border border-transparent p-4 text-left transition-colors"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <CategoryChip category={memory.category} />
        <ImportanceBadge importance={memory.importance} />
        {memory.status === "archived" ? (
          <span className="text-muted-foreground border-border rounded-full border px-2 py-0.5 text-[10px] font-medium">
            Archived
          </span>
        ) : null}
      </div>

      <p className="mt-3 line-clamp-3 text-sm text-balance">{memory.content}</p>

      <div className="text-muted-foreground mt-auto flex items-center justify-between gap-2 pt-3 text-[11px]">
        <span className="truncate">{getSourceLabel(memory.source)}</span>
        <span className="flex shrink-0 items-center gap-1">
          <Clock className="size-3" />
          {formatMonthYear(memory.created_at)}
        </span>
      </div>
    </button>
  );
}
