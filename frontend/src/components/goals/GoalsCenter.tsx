"use client";

import { useMemo, useState } from "react";
import { Plus, Target } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { GoalCard } from "@/components/goals/GoalCard";
import { GoalForm } from "@/components/goals/GoalForm";
import { getPriorityMeta } from "@/config/goals";
import { useGoalActions, useGoalsQuery, useGoalStats } from "@/lib/goals/useGoals";
import type { GoalCreateBody, GoalItem, GoalStatus } from "@/lib/api/resources";
import { cn } from "@/lib/utils";

type Filter = GoalStatus | "all";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "active", label: "Active" },
  { id: "completed", label: "Completed" },
  { id: "archived", label: "Archived" },
  { id: "all", label: "All" },
];

/**
 * Goals — the first-class goal management experience (M5). Create, edit,
 * complete, archive, and track progress (with milestones) for everything the
 * user is working toward. TanStack Query is the single source of truth.
 */
export function GoalsCenter() {
  const { data: goals, isLoading } = useGoalsQuery();
  const { data: stats } = useGoalStats();
  const actions = useGoalActions();

  const [filter, setFilter] = useState<Filter>("active");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<GoalItem | null>(null);

  const visible = useMemo(() => {
    const list = (goals ?? []).filter(
      (g) => filter === "all" || g.status === filter,
    );
    return [...list].sort((a, b) => {
      const rank =
        getPriorityMeta(b.priority).rank - getPriorityMeta(a.priority).rank;
      if (rank !== 0) return rank;
      return b.created_at.localeCompare(a.created_at);
    });
  }, [goals, filter]);

  function openCreate() {
    setEditing(null);
    setFormOpen(true);
  }

  function openEdit(goal: GoalItem) {
    setEditing(goal);
    setFormOpen(true);
  }

  function handleSubmit(body: GoalCreateBody) {
    if (editing) {
      actions.update(editing.id, body);
    } else {
      actions.create(body);
    }
  }

  const completionPct = stats ? Math.round(stats.completion_rate * 100) : 0;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
            Goals
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Everything you&apos;re working toward — tracked, with progress.
          </p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="size-4" />
          New goal
        </Button>
      </header>

      <div className="grid grid-cols-3 gap-2.5 sm:max-w-md">
        <Stat label="Active" value={stats?.active ?? 0} />
        <Stat label="Completed" value={stats?.completed ?? 0} />
        <Stat label="Completion" value={`${completionPct}%`} />
      </div>

      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            className={cn(
              "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
              filter === f.id
                ? "border-primary/40 bg-primary/15 text-primary"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-44 w-full rounded-2xl" />
          ))}
        </div>
      ) : visible.length === 0 ? (
        <EmptyState filter={filter} onCreate={openCreate} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visible.map((goal) => (
            <GoalCard key={goal.id} goal={goal} onEdit={openEdit} />
          ))}
        </div>
      )}

      <GoalForm
        open={formOpen}
        onOpenChange={setFormOpen}
        mode={editing ? "edit" : "add"}
        initial={editing}
        onSubmit={handleSubmit}
      />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="glass elevation-2 rounded-xl p-3">
      <div className="text-lg leading-none font-semibold tabular-nums">
        {value}
      </div>
      <div className="text-muted-foreground mt-1 text-xs">{label}</div>
    </div>
  );
}

function EmptyState({
  filter,
  onCreate,
}: {
  filter: Filter;
  onCreate: () => void;
}) {
  return (
    <div className="glass elevation-2 text-muted-foreground flex flex-col items-center gap-3 rounded-2xl px-6 py-12 text-center text-sm">
      <Target className="size-6 opacity-60" />
      <span className="text-balance">
        {filter === "active"
          ? "No active goals yet. Set one to start tracking progress."
          : `No ${filter} goals.`}
      </span>
      {filter === "active" ? (
        <Button onClick={onCreate} variant="outline" size="sm">
          <Plus className="size-3.5" />
          Create your first goal
        </Button>
      ) : null}
    </div>
  );
}
