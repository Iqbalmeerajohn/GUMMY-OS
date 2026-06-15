/**
 * Read/write API resources for the dashboard + workspace.
 *
 * Hand-typed against the backend Pydantic schemas (Phase 1–3). Swap to generated
 * types via `npm run gen:api` once the backend is running.
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
  agent_context: string;
  pinned: boolean;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MessageItem {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  seq: number;
  token_count: number | null;
  model: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  created_at: string;
}

export interface TurnResult {
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string;
  reply: string;
  model: string;
  memories_used: number;
  input_tokens: number;
  output_tokens: number;
  message_count: number;
}

// ── Memories / goals (dashboard + sidebars) ───────────────────────────────────

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

// ── Conversations / messages / turns (workspace) ──────────────────────────────

export function listConversations(limit = 30) {
  return apiFetch<Paginated<ConversationItem>>("/api/v1/conversations", {
    query: { limit },
  });
}

export const listRecentConversations = listConversations;

export function createConversation(agentContext = "general") {
  return apiFetch<ConversationItem>("/api/v1/conversations", {
    method: "POST",
    json: { agent_context: agentContext },
  });
}

export function listMessages(conversationId: string, limit = 100) {
  return apiFetch<Paginated<MessageItem>>(
    `/api/v1/conversations/${conversationId}/messages`,
    { query: { limit } },
  );
}

export function postTurn(conversationId: string, message: string) {
  return apiFetch<TurnResult>(
    `/api/v1/conversations/${conversationId}/messages`,
    { method: "POST", json: { message } },
  );
}
