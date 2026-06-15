/**
 * Minimal read-only API resources for the dashboard.
 *
 * Hand-typed against the backend Pydantic schemas (Phase 1–3). Replace with
 * generated types from `npm run gen:api` once the backend is running. Full CRUD
 * resource modules arrive with their feature milestones (M3+).
 */

import { apiFetch } from "@/lib/api/client";

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface MemoryItem {
  id: string;
  category: string;
  content: string;
  importance_score: number;
  confidence_score: number;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface GoalItem {
  id: string;
  title: string;
  description: string | null;
  status: string;
  priority: number;
  target_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationItem {
  id: string;
  title: string | null;
  status: string;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export function listMemories(limit = 5) {
  return apiFetch<Paginated<MemoryItem>>("/api/v1/memories", {
    query: { limit },
  });
}

export function listGoals(limit = 5) {
  return apiFetch<Paginated<GoalItem>>("/api/v1/goals", {
    query: { limit, status: "active" },
  });
}

export function listRecentConversations(limit = 5) {
  return apiFetch<Paginated<ConversationItem>>("/api/v1/conversations", {
    query: { limit },
  });
}
