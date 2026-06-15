"use client";

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/auth/AuthProvider";
import {
  listGoals,
  listMemories,
  listRecentConversations,
} from "@/lib/api/resources";

/**
 * Dashboard data hooks. Queries are enabled only when authenticated; failures
 * (e.g. backend not running) surface as `isError` so widgets show empty states.
 */

export function useRecentMemories() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["memories", "recent"],
    queryFn: () => listMemories(5),
    enabled: !!user,
    retry: false,
  });
}

export function useActiveGoals() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["goals", "active"],
    queryFn: () => listGoals(5),
    enabled: !!user,
    retry: false,
  });
}

export function useRecentConversations() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["conversations", "recent"],
    queryFn: () => listRecentConversations(5),
    enabled: !!user,
    retry: false,
  });
}
