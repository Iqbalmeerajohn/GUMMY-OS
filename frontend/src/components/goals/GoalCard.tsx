"use client";

import { useState } from "react";
import {
  Archive,
  CalendarClock,
  Check,
  ChevronDown,
  ListChecks,
  Pencil,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { GoalProgressBar } from "@/components/goals/GoalProgressBar";
import { GoalStatusBadge } from "@/components/goals/GoalStatusBadge";
import { MilestoneList } from "@/components/goals/MilestoneList";
import { getPriorityMeta } from "@/config/goals";
import { useGoalActions } from "@/lib/goals/useGoals";
import type { GoalItem } from "@/lib/api/resources";
import { formatFullDate } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Whether a target date is in the past (and the goal isn't done). */
function isOverdue(goal: GoalItem): boolean {
  if (!goal.target_date || goal.status !== "active") return false;
  return new Date(goal.target_date).getTime() < Date.now();
}

/** A single goal: status, priority, progress, due date, and milestones. */
export function GoalCard({
  goal,
  onEdit,
}: {
  goal: GoalItem;
  onEdit: (goal: GoalItem) => void;
}) {
  const actions = useGoalActions();
  const [expanded, setExpanded] = useState(false);
  const priority = getPriorityMeta(goal.priority);
  const completedCount = goal.milestones.filter((m) => m.completed).length;
  const overdue = isOverdue(goal);
  const isActive = goal.status === "active";

  return (
    <div className="glass elevation-2 flex h-full flex-col rounded-2xl p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium",
              priority.chip,
            )}
          >
            <span className={cn("size-1.5 rounded-full", priority.dot)} />
            {priority.label}
          </span>
          {goal.category ? (
            <span className="border-border text-muted-foreground rounded-full border px-2 py-0.5 text-[10px] font-medium">
              {goal.category}
            </span>
          ) : null}
        </div>
        <GoalStatusBadge status={goal.status} />
      </div>

      <h3 className="mt-2.5 text-sm font-semibold text-balance">
        {goal.title}
      </h3>
      {goal.description ? (
        <p className="text-muted-foreground mt-1 line-clamp-2 text-xs">
          {goal.description}
        </p>
      ) : null}

      <div className="mt-3">
        <GoalProgressBar value={goal.progress_percentage} />
      </div>

      <div className="text-muted-foreground mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
        {goal.milestones.length > 0 ? (
          <span className="inline-flex items-center gap-1">
            <ListChecks className="size-3" />
            {completedCount}/{goal.milestones.length} milestones
          </span>
        ) : null}
        {goal.target_date ? (
          <span
            className={cn(
              "inline-flex items-center gap-1",
              overdue && "text-destructive",
            )}
          >
            <CalendarClock className="size-3" />
            {overdue ? "Overdue · " : "Due "}
            {formatFullDate(goal.target_date)}
          </span>
        ) : null}
      </div>

      <div className="mt-auto pt-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-primary inline-flex items-center gap-1 text-xs font-medium hover:underline"
          aria-expanded={expanded}
        >
          <ChevronDown
            className={cn(
              "size-3.5 transition-transform",
              expanded && "rotate-180",
            )}
          />
          Milestones
        </button>

        {expanded ? (
          <div className="border-border/50 mt-3 border-t pt-3">
            <MilestoneList goalId={goal.id} milestones={goal.milestones} />
          </div>
        ) : null}

        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {isActive ? (
            <Button
              size="xs"
              variant="outline"
              onClick={() => actions.complete(goal.id)}
            >
              <Check className="size-3" />
              Complete
            </Button>
          ) : null}
          <Button
            size="xs"
            variant="ghost"
            aria-label="Edit goal"
            onClick={() => onEdit(goal)}
          >
            <Pencil className="size-3" />
            Edit
          </Button>
          {goal.status !== "archived" ? (
            <Button
              size="xs"
              variant="ghost"
              aria-label="Archive goal"
              onClick={() => actions.archive(goal.id)}
            >
              <Archive className="size-3" />
              Archive
            </Button>
          ) : null}
          <Button
            size="icon-xs"
            variant="ghost"
            aria-label="Delete goal"
            className="text-muted-foreground/70 hover:text-destructive ml-auto"
            onClick={() => actions.remove(goal.id)}
          >
            <Trash2 className="size-3" />
          </Button>
        </div>
      </div>
    </div>
  );
}
