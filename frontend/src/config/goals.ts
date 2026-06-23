/**
 * Goals presentation config — the single source for how goal priority and
 * status render (labels, ordering, tone). Mirrors the backend enums
 * (`GoalPriority`, `GoalStatus`) so the UI and API never drift.
 */

import type { GoalPriority, GoalStatus } from "@/lib/api/resources";

export interface PriorityMeta {
  id: GoalPriority;
  label: string;
  /** Higher = more important (sort order on the Goals page). */
  rank: number;
  /** Tailwind classes for the priority chip. */
  chip: string;
  dot: string;
}

export const GOAL_PRIORITIES: PriorityMeta[] = [
  {
    id: "high",
    label: "High",
    rank: 3,
    chip: "border-destructive/30 bg-destructive/10 text-destructive",
    dot: "bg-destructive",
  },
  {
    id: "medium",
    label: "Medium",
    rank: 2,
    chip: "border-primary/30 bg-primary/10 text-primary",
    dot: "bg-primary",
  },
  {
    id: "low",
    label: "Low",
    rank: 1,
    chip: "border-border bg-muted/40 text-muted-foreground",
    dot: "bg-muted-foreground/60",
  },
];

const PRIORITY_BY_ID: Record<GoalPriority, PriorityMeta> = Object.fromEntries(
  GOAL_PRIORITIES.map((p) => [p.id, p]),
) as Record<GoalPriority, PriorityMeta>;

export function getPriorityMeta(priority: GoalPriority): PriorityMeta {
  return PRIORITY_BY_ID[priority] ?? PRIORITY_BY_ID.medium;
}

export interface StatusMeta {
  id: GoalStatus;
  label: string;
  /** Tailwind classes for the status badge. */
  badge: string;
}

export const GOAL_STATUSES: StatusMeta[] = [
  {
    id: "active",
    label: "Active",
    badge: "border-primary/30 bg-primary/10 text-primary",
  },
  {
    id: "completed",
    label: "Completed",
    badge: "border-emerald-500/30 bg-emerald-500/10 text-emerald-500",
  },
  {
    id: "archived",
    label: "Archived",
    badge: "border-border bg-muted/40 text-muted-foreground",
  },
];

const STATUS_BY_ID: Record<GoalStatus, StatusMeta> = Object.fromEntries(
  GOAL_STATUSES.map((s) => [s.id, s]),
) as Record<GoalStatus, StatusMeta>;

export function getStatusMeta(status: GoalStatus): StatusMeta {
  return STATUS_BY_ID[status] ?? STATUS_BY_ID.active;
}

/** Common, free-form category suggestions surfaced in the goal form. */
export const GOAL_CATEGORY_SUGGESTIONS = [
  "Career",
  "Health",
  "Learning",
  "Finance",
  "Personal",
  "Project",
] as const;
