"use client";

import { useState } from "react";
import { Check, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useGoalActions } from "@/lib/goals/useGoals";
import type { MilestoneItem } from "@/lib/api/resources";
import { cn } from "@/lib/utils";

/**
 * The checklist of a goal's milestones. Toggling completion recomputes the
 * goal's progress server-side (the query is invalidated on success). Adding /
 * removing milestones flows through the same actions.
 */
export function MilestoneList({
  goalId,
  milestones,
}: {
  goalId: string;
  milestones: MilestoneItem[];
}) {
  const actions = useGoalActions();
  const [title, setTitle] = useState("");

  function handleAdd() {
    const trimmed = title.trim();
    if (!trimmed) return;
    actions.addMilestone(goalId, trimmed);
    setTitle("");
  }

  return (
    <div className="space-y-2">
      {milestones.length > 0 ? (
        <ul className="space-y-1.5">
          {milestones.map((m) => (
            <li key={m.id} className="flex items-center gap-2">
              <button
                type="button"
                aria-label={
                  m.completed ? "Mark incomplete" : "Mark complete"
                }
                onClick={() => actions.toggleMilestone(m.id, !m.completed)}
                className={cn(
                  "grid size-4.5 shrink-0 place-items-center rounded-[6px] border transition-colors",
                  m.completed
                    ? "border-emerald-500 bg-emerald-500 text-white"
                    : "border-border hover:border-primary",
                )}
              >
                {m.completed ? <Check className="size-3" /> : null}
              </button>
              <span
                className={cn(
                  "flex-1 text-sm",
                  m.completed && "text-muted-foreground line-through",
                )}
              >
                {m.title}
              </span>
              <button
                type="button"
                aria-label="Delete milestone"
                onClick={() => actions.removeMilestone(m.id)}
                className="text-muted-foreground/60 hover:text-destructive transition-colors"
              >
                <Trash2 className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-xs">
          No milestones yet. Break this goal into steps to track progress
          automatically.
        </p>
      )}

      <div className="flex items-center gap-2 pt-1">
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              handleAdd();
            }
          }}
          placeholder="Add a milestone…"
          className="border-input focus-visible:border-ring focus-visible:ring-ring/50 dark:bg-input/30 h-7 flex-1 rounded-lg border bg-transparent px-2.5 text-sm outline-none focus-visible:ring-3"
        />
        <Button
          size="icon-sm"
          variant="outline"
          aria-label="Add milestone"
          onClick={handleAdd}
          disabled={!title.trim()}
        >
          <Plus className="size-3.5" />
        </Button>
      </div>
    </div>
  );
}
