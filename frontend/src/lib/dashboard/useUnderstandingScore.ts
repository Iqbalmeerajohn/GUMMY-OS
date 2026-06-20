"use client";

import { useMemo } from "react";

import {
  useActiveGoals,
  useRecentConversations,
} from "@/lib/hooks/useDashboard";
import { useTopMemories } from "@/lib/memory/useMemory";
import { useProfile } from "@/lib/profile/useProfile";
import {
  computeUnderstandingScore,
  type UnderstandingScore,
} from "@/lib/dashboard/understandingScore";

// Large cap so we score against the full active memory set (the backend page
// size is 100); maturity saturates well before this anyway.
const ALL_ACTIVE = 1000;

/**
 * Live User Understanding Score, assembled entirely from real data: the saved
 * profile, the user's active memories (categories + content), and backend goal
 * / conversation counts. No values are hardcoded — see `computeUnderstandingScore`.
 */
export function useUnderstandingScore(): UnderstandingScore {
  const { data: profile } = useProfile();
  const memories = useTopMemories(ALL_ACTIVE);
  const goals = useActiveGoals();
  const conversations = useRecentConversations();

  const goalsTotal = goals.data?.total ?? 0;
  const activityTotal = conversations.data?.total ?? 0;
  const displayName = profile?.display_name ?? null;

  return useMemo(() => {
    const memoriesByCategory: Record<string, number> = {};
    for (const m of memories) {
      memoriesByCategory[m.category] =
        (memoriesByCategory[m.category] ?? 0) + 1;
    }
    return computeUnderstandingScore({
      displayName,
      memoryContents: memories.map((m) => m.content),
      memoriesByCategory,
      memoryCount: memories.length,
      activeGoalsCount: goalsTotal,
      recentActivityCount: activityTotal,
    });
  }, [displayName, memories, goalsTotal, activityTotal]);
}
