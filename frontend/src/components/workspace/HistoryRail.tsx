"use client";

import { useState } from "react";
import { Plus, Search } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useConversations } from "@/lib/hooks/useChat";
import { formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Conversation history + search + new (the left rail). */
export function HistoryRail({
  activeId,
  onSelect,
  onNew,
}: {
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const { data, isLoading } = useConversations();
  const [q, setQ] = useState("");

  const items = (data?.items ?? []).filter((c) =>
    (c.title ?? "Untitled conversation")
      .toLowerCase()
      .includes(q.toLowerCase()),
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="space-y-3 p-3">
        <button
          onClick={onNew}
          className={cn(buttonVariants({ size: "sm" }), "w-full gap-1.5")}
        >
          <Plus className="size-4" />
          New conversation
        </button>
        <div className="relative">
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search"
            className="border-input focus-visible:border-ring focus-visible:ring-ring/50 h-8 w-full rounded-lg border bg-transparent pr-2 pl-8 text-sm outline-none focus-visible:ring-2"
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {isLoading ? (
          <div className="space-y-2 px-1">
            <Skeleton className="h-12 w-full rounded-lg" />
            <Skeleton className="h-12 w-full rounded-lg" />
            <Skeleton className="h-12 w-full rounded-lg" />
          </div>
        ) : items.length === 0 ? (
          <p className="text-muted-foreground px-3 py-6 text-center text-xs text-balance">
            No conversations yet. Start one to see it here.
          </p>
        ) : (
          <ul className="space-y-1">
            {items.map((c) => (
              <li key={c.id}>
                <button
                  onClick={() => onSelect(c.id)}
                  className={cn(
                    "w-full rounded-lg px-3 py-2 text-left transition-colors",
                    c.id === activeId
                      ? "bg-accent text-accent-foreground"
                      : "hover:bg-muted/60",
                  )}
                >
                  <span className="block truncate text-sm font-medium">
                    {c.title ?? "Untitled conversation"}
                  </span>
                  <span className="text-muted-foreground text-xs">
                    {formatRelativeTime(c.last_message_at) || "New"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
