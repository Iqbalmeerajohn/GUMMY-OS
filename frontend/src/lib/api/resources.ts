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

export type GoalStatus = "active" | "completed" | "archived";
export type GoalPriority = "low" | "medium" | "high";

export interface MilestoneItem {
  id: string;
  goal_id: string;
  title: string;
  completed: boolean;
  completed_at: string | null;
  order_index: number;
  created_at: string;
  updated_at: string;
}

export interface GoalItem {
  id: string;
  user_id: string;
  title: string;
  description: string | null;
  category: string | null;
  status: GoalStatus;
  priority: GoalPriority;
  agent_context: string;
  progress_percentage: number;
  target_date: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  milestones: MilestoneItem[];
}

export interface GoalStats {
  active: number;
  completed: number;
  archived: number;
  total: number;
  completion_rate: number;
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
  /** Persisted reply metadata. M8 carries `agent_key` (which agent replied). */
  metadata: Record<string, unknown> | null;
  created_at: string;
}

/**
 * A goal-like statement detected in a user message (M5.5 Goal Intelligence).
 * Surfaced for explicit confirmation — never auto-created.
 */
export interface GoalCandidate {
  title: string;
  description: string | null;
  priority: GoalPriority;
  target_date: string | null;
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
  /** A detected goal candidate (M5.5), or null when the message isn't a goal. */
  goal_candidate: GoalCandidate | null;
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

export interface GoalListParams {
  limit?: number;
  offset?: number;
  status?: GoalStatus;
}

/** Full goal list with optional status filter (Goals page). */
export function fetchGoals(params: GoalListParams = {}) {
  const { limit = 100, offset = 0, status } = params;
  return apiFetch<Paginated<GoalItem>>("/api/v1/goals", {
    query: { limit, offset, status },
  });
}

export function fetchGoalStats() {
  return apiFetch<GoalStats>("/api/v1/goals/stats");
}

export interface GoalCreateBody {
  title: string;
  description?: string | null;
  category?: string | null;
  priority?: GoalPriority;
  target_date?: string | null;
}

export interface GoalUpdateBody {
  title?: string;
  description?: string | null;
  category?: string | null;
  status?: GoalStatus;
  priority?: GoalPriority;
  progress_percentage?: number;
  target_date?: string | null;
}

export function createGoal(body: GoalCreateBody) {
  return apiFetch<GoalItem>("/api/v1/goals", { method: "POST", json: body });
}

export function updateGoal(id: string, body: GoalUpdateBody) {
  return apiFetch<GoalItem>(`/api/v1/goals/${id}`, {
    method: "PATCH",
    json: body,
  });
}

export function completeGoal(id: string) {
  return apiFetch<GoalItem>(`/api/v1/goals/${id}/complete`, {
    method: "POST",
  });
}

export function archiveGoal(id: string) {
  return apiFetch<GoalItem>(`/api/v1/goals/${id}/archive`, { method: "POST" });
}

export function deleteGoal(id: string) {
  return apiFetch<void>(`/api/v1/goals/${id}`, { method: "DELETE" });
}

// ── Goal Intelligence (M5.5): create / dismiss from a conversation ────────────

export interface GoalFromConversationBody {
  title: string;
  description?: string | null;
  priority?: GoalPriority;
  target_date?: string | null;
  category?: string | null;
  conversation_id?: string | null;
}

export interface GoalCandidateDismissBody {
  title: string;
  priority?: GoalPriority;
  target_date?: string | null;
  conversation_id?: string | null;
}

/** Accept a detected candidate: create the goal (traced as goal_source=conversation). */
export function createGoalFromConversation(body: GoalFromConversationBody) {
  return apiFetch<GoalItem>("/api/v1/goals/from-conversation", {
    method: "POST",
    json: body,
  });
}

/** Dismiss a detected candidate: records the rejection, creates nothing. */
export function dismissGoalCandidate(body: GoalCandidateDismissBody) {
  return apiFetch<void>("/api/v1/goals/from-conversation/dismiss", {
    method: "POST",
    json: body,
  });
}

// ── Milestones ────────────────────────────────────────────────────────────────

export function createMilestone(goalId: string, title: string) {
  return apiFetch<MilestoneItem>(`/api/v1/goals/${goalId}/milestones`, {
    method: "POST",
    json: { title },
  });
}

export interface MilestoneUpdateBody {
  title?: string;
  completed?: boolean;
  order_index?: number;
}

export function updateMilestone(id: string, body: MilestoneUpdateBody) {
  return apiFetch<MilestoneItem>(`/api/v1/milestones/${id}`, {
    method: "PATCH",
    json: body,
  });
}

export function deleteMilestone(id: string) {
  return apiFetch<void>(`/api/v1/milestones/${id}`, { method: "DELETE" });
}

// ── Files (M6 Files System) ───────────────────────────────────────────────────

export type FileUploadStatus = "pending" | "uploaded" | "failed";
export type FileProcessingStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed";

export interface FileItem {
  id: string;
  user_id: string;
  filename: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  upload_status: FileUploadStatus;
  processing_status: FileProcessingStatus;
  chunk_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface FileChunkItem {
  id: string;
  file_id: string;
  chunk_index: number;
  content: string;
  token_count: number;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
}

export interface FileStats {
  total: number;
  recent: FileItem[];
}

export interface FileListParams {
  limit?: number;
  offset?: number;
}

/** Full file list (Files page). Newest first. */
export function fetchFiles(params: FileListParams = {}) {
  const { limit = 100, offset = 0 } = params;
  return apiFetch<Paginated<FileItem>>("/api/v1/files", {
    query: { limit, offset },
  });
}

/** Recent files + total count (dashboard widget). */
export function fetchFileStats() {
  return apiFetch<FileStats>("/api/v1/files/stats");
}

export function fetchFile(id: string) {
  return apiFetch<FileItem>(`/api/v1/files/${id}`);
}

export function fetchFileChunks(id: string, limit = 50, offset = 0) {
  return apiFetch<Paginated<FileChunkItem>>(`/api/v1/files/${id}/chunks`, {
    query: { limit, offset },
  });
}

/**
 * Upload a file as multipart/form-data. Bypasses `apiFetch` (which is JSON-only)
 * and uses raw fetch with the bearer token, mirroring `streamTurn`.
 */
export async function uploadFile(file: File): Promise<FileItem> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(apiUrl("/api/v1/files/upload"), {
    method: "POST",
    headers: { ...(await authHeaders()) },
    body: form,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const code = data?.code ?? data?.error?.code ?? "upload_error";
    const message =
      data?.error?.message ??
      data?.message ??
      res.statusText ??
      "Upload failed";
    throw new ApiError(res.status, code, message, data);
  }
  return data as FileItem;
}

export function deleteFile(id: string) {
  return apiFetch<void>(`/api/v1/files/${id}`, { method: "DELETE" });
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

export function postTurn(
  conversationId: string,
  message: string,
  attachmentFileIds?: string[],
  agent?: string,
) {
  return apiFetch<TurnResult>(
    `/api/v1/conversations/${conversationId}/messages`,
    {
      method: "POST",
      json: {
        message,
        ...(attachmentFileIds?.length
          ? { attachment_file_ids: attachmentFileIds }
          : {}),
        // M8 manual override: pin an agent (Auto omits this → Router decides).
        ...(agent ? { agent } : {}),
      },
    },
  );
}

/** The selectable agents the backend advertises (workspace selector / badges). */
export interface AgentInfo {
  name: string;
  display_name: string;
  description: string;
  keywords: string[];
}

/** List the available agents (General + the five M8 specialists). */
export function listAgents() {
  return apiFetch<AgentInfo[]>("/api/v1/agents");
}

/** Routing diagnostics: which agent the Router would pick for a query, and why. */
export function agentDiagnostics(q: string) {
  return apiFetch<{
    query: string;
    selected_agent: string;
    confidence: number;
    reason: string;
    available_agents: AgentInfo[];
  }>("/api/v1/agents/diagnostics", { query: { q } });
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

/** One live web source used to ground a reply (M8.5 🌐 Web Sources). */
export interface WebSource {
  title: string;
  url: string;
  domain: string;
}

/** What GUMMY is doing right now — safe to display, never reasoning. */
export interface ToolActivity {
  /** The tool's registry key, e.g. "file_search". */
  tool?: string;
  /** Human label for the tool, e.g. "File Search". */
  label?: string;
  stage?: string;
}

/** A single Server-Sent Event from the streaming turn endpoint. */
export interface StreamEvent {
  /**
   * `status` and `tool_status` are progress; `delta` is reply text; `done` is
   * terminal. Progress events carry a stage name and (for tools) a tool key
   * and label — deliberately never the model's reasoning or tool arguments.
   */
  type: "delta" | "done" | "status" | "tool_status";
  text?: string;
  /** Orchestrator stage: understanding | retrieving_context | answering | … */
  stage?: string;
  /** Plan shape for this turn: single | pipeline | parallel. */
  shape?: string;
  /** On a parallel delegation, every branch agent running at once. */
  agents?: string[];
  /** Tool stage: tool_requested | tool_running | tool_completed | tool_failed |
   * approval_required. */
  tool?: string;
  label?: string;
  duration_ms?: number;
  approval_id?: string;
  /** Every stage this turn passed through (on `done`). */
  stages?: string[];
  /** Tools that ran, with how each ended (on `done`). */
  tools?: ToolActivity[];
  conversation_id?: string;
  user_message_id?: string;
  assistant_message_id?: string;
  model?: string;
  memories_used?: number;
  /** Short contents of the memories used to ground the reply (Memory Used UI). */
  memories?: string[];
  message_count?: number;
  /** M8: the agent that answered (Auto-routed or overridden), or null (legacy). */
  agent?: string | null;
  /** M8.5: live web sources used to ground the reply (🌐 Web Sources), or []. */
  web_sources?: WebSource[];
  /** A goal-like statement detected in the user's message (M5.5), or null. */
  goal_candidate?: GoalCandidate | null;
}

/**
 * Stream a turn as Server-Sent Events. Yields `delta` events (live tokens) then
 * a terminal `done` event with persisted ids + the memories used to ground it.
 */
export async function* streamTurn(
  conversationId: string,
  message: string,
  signal?: AbortSignal,
  attachmentFileIds?: string[],
  agent?: string,
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
      body: JSON.stringify({
        message,
        ...(attachmentFileIds?.length
          ? { attachment_file_ids: attachmentFileIds }
          : {}),
        // M8 manual override: pin an agent (Auto omits this → Router decides).
        ...(agent ? { agent } : {}),
      }),
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

// ── Connectors ────────────────────────────────────────────────────────────────

export interface CalendarImportResult {
  imported: number;
  preview: string[];
}

/**
 * Import past events from a Google Calendar secret iCal address (or any .ics
 * feed). Re-importing is safe — the backend reinforces facts it already holds.
 */
export function importCalendar(icsUrl: string) {
  return apiFetch<CalendarImportResult>("/api/v1/connectors/calendar", {
    method: "POST",
    json: { ics_url: icsUrl },
  });
}

// ── Automations ──────────────────────────────────────────────────────────────

/** A scheduled task GUMMY runs locally. */
export interface AutomationItem {
  id: string;
  name: string;
  description: string | null;
  kind: string;
  schedule: string;
  status: string;
  enabled: boolean;
  timezone: string;
  next_run_at: string | null;
  last_run_at: string | null;
  last_error: string | null;
  created_at: string;
}

export interface AutomationListResult {
  items: AutomationItem[];
  total: number;
}

export function listAutomations() {
  return apiFetch<AutomationListResult>("/api/v1/automations", {
    query: { limit: 100 },
  });
}

export function toggleAutomation(id: string, enabled: boolean) {
  return apiFetch<AutomationItem>(`/api/v1/automations/${id}/toggle`, {
    method: "POST",
    json: { enabled },
  });
}

export function deleteAutomation(id: string) {
  return apiFetch<void>(`/api/v1/automations/${id}`, { method: "DELETE" });
}
