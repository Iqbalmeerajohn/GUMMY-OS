"use client";

import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { useAuth } from "@/components/auth/AuthProvider";
import {
  archiveGoal,
  completeGoal,
  createGoal,
  createMilestone,
  deleteGoal,
  deleteMilestone,
  fetchGoalStats,
  fetchGoals,
  updateGoal,
  updateMilestone,
  type GoalCreateBody,
  type GoalItem,
  type GoalUpdateBody,
  type MilestoneUpdateBody,
} from "@/lib/api/resources";
import { analytics, AnalyticsEvent } from "@/lib/analytics";

const GOALS_KEY = ["goals", "all"] as const;
const STATS_KEY = ["goals", "stats"] as const;

/**
 * The user's goals from the backend (all statuses, so the page can filter and
 * compute counts). Single source of truth; every goal surface reads this query.
 */
export function useGoalsQuery() {
  const { user } = useAuth();
  return useQuery({
    queryKey: GOALS_KEY,
    queryFn: async (): Promise<GoalItem[]> => {
      const page = await fetchGoals({ limit: 100 });
      return page.items;
    },
    enabled: !!user,
    retry: false,
  });
}

/** Aggregate goal counts + completion rate (dashboard + page header). */
export function useGoalStats() {
  const { user } = useAuth();
  return useQuery({
    queryKey: STATS_KEY,
    queryFn: fetchGoalStats,
    enabled: !!user,
    retry: false,
  });
}

/** A single goal by id from the cached list (or undefined). */
export function useGoal(id: string | null): GoalItem | undefined {
  const { data } = useGoalsQuery();
  return useMemo(
    () => (id ? data?.find((g) => g.id === id) : undefined),
    [data, id],
  );
}

/**
 * Goal + milestone write actions, backed by the API and stable across renders.
 * Each successful mutation invalidates the goals queries and fires the matching
 * PostHog event through the shared analytics seam.
 */
export function useGoalActions() {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["goals"] });
  };
  const onError = (err: unknown) => {
    analytics.captureException(err, { context: "goal_write_failed" });
    toast.error(err instanceof Error ? err.message : "Something went wrong.");
  };

  const create = useMutation({
    mutationFn: (body: GoalCreateBody) => createGoal(body),
    onSuccess: (goal) => {
      analytics.track(AnalyticsEvent.GoalCreated, {
        goal_id: goal.id,
        priority: goal.priority,
        category: goal.category,
      });
      invalidate();
    },
    onError,
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: GoalUpdateBody }) =>
      updateGoal(id, body),
    onSuccess: (goal) => {
      analytics.track(AnalyticsEvent.GoalUpdated, { goal_id: goal.id });
      invalidate();
    },
    onError,
  });

  const complete = useMutation({
    mutationFn: (id: string) => completeGoal(id),
    onSuccess: (goal) => {
      analytics.track(AnalyticsEvent.GoalCompleted, { goal_id: goal.id });
      invalidate();
    },
    onError,
  });

  const archive = useMutation({
    mutationFn: (id: string) => archiveGoal(id),
    onSuccess: (goal) => {
      analytics.track(AnalyticsEvent.GoalArchived, { goal_id: goal.id });
      invalidate();
    },
    onError,
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteGoal(id),
    onSuccess: invalidate,
    onError,
  });

  const addMilestone = useMutation({
    mutationFn: ({ goalId, title }: { goalId: string; title: string }) =>
      createMilestone(goalId, title),
    onSuccess: (milestone) => {
      analytics.track(AnalyticsEvent.MilestoneCreated, {
        milestone_id: milestone.id,
        goal_id: milestone.goal_id,
      });
      invalidate();
    },
    onError,
  });

  const editMilestone = useMutation({
    mutationFn: ({ id, body }: { id: string; body: MilestoneUpdateBody }) =>
      updateMilestone(id, body),
    onSuccess: (milestone) => {
      if (milestone.completed) {
        analytics.track(AnalyticsEvent.MilestoneCompleted, {
          milestone_id: milestone.id,
          goal_id: milestone.goal_id,
        });
      }
      invalidate();
    },
    onError,
  });

  const removeMilestone = useMutation({
    mutationFn: (id: string) => deleteMilestone(id),
    onSuccess: invalidate,
    onError,
  });

  return useMemo(
    () => ({
      create: (body: GoalCreateBody) => create.mutate(body),
      update: (id: string, body: GoalUpdateBody) =>
        update.mutate({ id, body }),
      complete: (id: string) => complete.mutate(id),
      archive: (id: string) => archive.mutate(id),
      remove: (id: string) => remove.mutate(id),
      addMilestone: (goalId: string, title: string) =>
        addMilestone.mutate({ goalId, title }),
      toggleMilestone: (id: string, completed: boolean) =>
        editMilestone.mutate({ id, body: { completed } }),
      removeMilestone: (id: string) => removeMilestone.mutate(id),
      isCreating: create.isPending,
    }),
    [create, update, complete, archive, remove, addMilestone, editMilestone, removeMilestone],
  );
}
