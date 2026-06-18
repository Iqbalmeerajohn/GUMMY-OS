/**
 * Read/write API resources for the dashboard + workspace.
 *
 * Hand-typed against the backend Pydantic schemas (Phase 1–3). Swap to generated
 * types via `npm run gen:api` once the backend is running.
 */

import { ApiError, apiFetch, apiUrl, authHeaders } from "@/lib/api/client";

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

export interface MemoryListParams {
  limit?: number;
  offset?: number;
  status?: string;
  category?: string;
}

/** Full memory list with filters (Memory Center). Defaults to all statuses. */
export function fetchMemories(params: MemoryListParams = {}) {
  const { limit = 100, offset = 0, status, category } = params;
  return apiFetch<Paginated<MemoryItem>>("/api/v1/memories", {
    query: { limit, offset, status, category },
  });
}

export interface MemoryCreateBody {
  category: string;
  content: string;
  importance_score?: number;
}

export interface MemoryUpdateBody {
  content?: string;
  category?: string;
  importance_score?: number;
}

export function createMemory(body: MemoryCreateBody) {
  return apiFetch<MemoryItem>("/api/v1/memories", {
    method: "POST",
    json: body,
  });
}

export function updateMemory(id: string, body: MemoryUpdateBody) {
  return apiFetch<MemoryItem>(`/api/v1/memories/${id}`, {
    method: "PATCH",
    json: body,
  });
}

export function archiveMemory(id: string) {
  return apiFetch<MemoryItem>(`/api/v1/memories/${id}/archive`, {
    method: "POST",
  });
}

export function restoreMemory(id: string) {
  return apiFetch<MemoryItem>(`/api/v1/memories/${id}/restore`, {
    method: "POST",
  });
}

export function deleteMemory(id: string) {
  return apiFetch<void>(`/api/v1/memories/${id}`, { method: "DELETE" });
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

export interface ConversationUpdateBody {
  title?: string;
  pinned?: boolean;
  status?: "active" | "archived";
}

export function updateConversation(id: string, body: ConversationUpdateBody) {
  return apiFetch<ConversationItem>(`/api/v1/conversations/${id}`, {
    method: "PATCH",
    json: body,
  });
}

export function deleteConversation(id: string) {
  return apiFetch<void>(`/api/v1/conversations/${id}`, { method: "DELETE" });
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

// ── Unified search (conversations + messages + memories) ──────────────────────

export interface ConversationSearchHit {
  conversation_id: string;
  title: string | null;
  status: string;
  last_message_at: string | null;
  message_count: number;
  score: number;
  match_message_id: string | null;
}

export interface MessageSearchHit {
  message_id: string;
  conversation_id: string;
  conversation_title: string | null;
  role: string;
  content: string;
  score: number;
}

export interface MemorySearchHit {
  id: string;
  category: string;
  content: string;
  similarity_score: number;
}

/** Hybrid (keyword + semantic) conversation search. */
export function searchConversations(q: string, limit = 8) {
  return apiFetch<{ results: ConversationSearchHit[] }>(
    "/api/v1/conversations/search",
    { query: { q, limit } },
  );
}

/** Full-text search over individual messages (returns content for snippets). */
export function searchMessages(q: string, limit = 8) {
  return apiFetch<{ results: MessageSearchHit[] }>(
    "/api/v1/conversations/message-search",
    { query: { q, limit } },
  );
}

/** Semantic search over the user's memories. */
export function searchMemories(q: string, limit = 8) {
  return apiFetch<{ results: MemorySearchHit[] }>("/api/v1/memories/search", {
    method: "POST",
    json: { query: q, limit },
  });
}

/** A single Server-Sent Event from the streaming turn endpoint. */
export interface StreamEvent {
  type: "delta" | "done";
  text?: string;
  conversation_id?: string;
  user_message_id?: string;
  assistant_message_id?: string;
  model?: string;
  memories_used?: number;
  /** Short contents of the memories used to ground the reply (Memory Used UI). */
  memories?: string[];
  message_count?: number;
}

/**
 * Stream a turn as Server-Sent Events. Yields `delta` events (live tokens) then
 * a terminal `done` event with persisted ids + the memories used to ground it.
 */
export async function* streamTurn(
  conversationId: string,
  message: string,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(
    apiUrl(`/api/v1/conversations/${conversationId}/messages/stream`),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...(await authHeaders()),
      },
      body: JSON.stringify({ message }),
      signal,
    },
  );
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, "stream_error", "Streaming failed.");
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line; keep any trailing partial.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (payload) yield JSON.parse(payload) as StreamEvent;
    }
  }
}
