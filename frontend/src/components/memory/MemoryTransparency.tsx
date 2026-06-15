"use client";

import { Sparkles } from "lucide-react";

import { getIcon } from "@/lib/icons";
import { cn } from "@/lib/utils";
import type { MemoryCategory } from "@/config/memory";
import { useTransparency } from "@/lib/memory/useMemory";

/**
 * "What GUMMY knows about you" (Deliverable 11). Assembled from stored memories
 * — no AI generation. Builds trust by making memory explainable. Clicking a
 * group filters the list to that category.
 */
export function MemoryTransparency({
  onSelectCategory,
}: {
  onSelectCategory?: (category: MemoryCategory) => void;
}) {
  const { headline, groups } = useTransparency();

  if (groups.length === 0) return null;

  return (
    <section className="glass elevation-2 rounded-2xl p-5">
      <div className="flex items-center gap-2">
        <span className="bg-accent text-primary grid size-8 place-items-center rounded-xl">
          <Sparkles className="size-4" />
        </span>
        <div>
          <h2 className="font-heading text-sm font-semibold">
            What GUMMY knows about you
          </h2>
          <p className="text-muted-foreground text-xs">{headline}</p>
        </div>
      </div>

      <div className="mt-4 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {groups.map((g) => {
          const Icon = getIcon(g.icon);
          return (
            <button
              key={g.category}
              type="button"
              onClick={() => onSelectCategory?.(g.category as MemoryCategory)}
              className="border-border/50 bg-background/40 hover:border-primary/40 rounded-xl border p-3 text-left transition-colors"
            >
              <div className="flex items-center justify-between gap-2">
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium",
                    g.accent,
                  )}
                >
                  <Icon className="size-3" />
                  {g.label}
                </span>
                <span className="text-muted-foreground text-xs font-medium">
                  {g.count}
                </span>
              </div>
              <ul className="mt-2 space-y-1">
                {g.highlights.map((m) => (
                  <li
                    key={m.id}
                    className="text-muted-foreground line-clamp-1 text-xs"
                  >
                    {m.content}
                  </li>
                ))}
              </ul>
            </button>
          );
        })}
      </div>
    </section>
  );
}
