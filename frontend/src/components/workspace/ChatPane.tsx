"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Brain,
  Briefcase,
  ChevronDown,
  FileSearch,
  GraduationCap,
  Hammer,
  PanelLeft,
  PanelRight,
  Sparkles,
  Telescope,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth/AuthProvider";
import { LivingOrb } from "@/components/brand/LivingOrb";
import { AgentSelect } from "@/components/workspace/AgentSelect";
import { Composer } from "@/components/workspace/Composer";
import { MessageBubble } from "@/components/workspace/MessageBubble";
import { useCreateConversation, useMessages } from "@/lib/hooks/useChat";
import { useSnapshotMemories } from "@/lib/memory/useMemory";
import { greetingName } from "@/lib/profile/displayName";
import { useProfile } from "@/lib/profile/useProfile";
import { postTurn, streamTurn } from "@/lib/api/resources";
import { modeToAgentContext, previewRoutedAgents } from "@/lib/chat/routing";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

// Diagnostic: flip to true to trace where each message bubble comes from
// (optimistic = local user echo, stream = live tokens, server = persisted refetch).
// Off by default so production stays quiet.
const LOG_MESSAGE_SOURCES = false;
function logMsg(
  id: string,
  role: string,
  source: "optimistic" | "stream" | "server",
) {
  if (LOG_MESSAGE_SOURCES) {
    console.debug(`[msg] id=${id} role=${role} source=${source}`);
  }
}

const AGENT_EMOJI: Record<string, string> = {
  General: "🧠",
  Learning: "🎓",
  Career: "💼",
  Research: "🔬",
  Builder: "🛠️",
  Content: "✍️",
  Sales: "📈",
  Admin: "🗂️",
};

const STREAM_PHASES = [
  "Thinking…",
  "Consulting memory…",
  "Using agent…",
  "Generating response…",
];

const QUICK_ACTIONS = [
  { icon: Telescope, label: "Research something", prompt: "Research " },
  { icon: Sparkles, label: "Plan my day", prompt: "Help me plan my day." },
  { icon: Hammer, label: "Build a project", prompt: "Help me build " },
  { icon: GraduationCap, label: "Learn a topic", prompt: "Teach me about " },
  { icon: FileSearch, label: "Analyze a document", prompt: "Analyze this: " },
  { icon: Briefcase, label: "Find opportunities", prompt: "Find opportunities for " },
];

/** A single compact agent chip: "🧠 General Agent". */
function AgentChip({ label }: { label: string }) {
  const emoji = AGENT_EMOJI[label] ?? "🧠";
  return (
    <span className="border-primary/25 bg-primary/8 text-primary/90 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium">
      <span aria-hidden>{emoji}</span>
      {label} Agent
    </span>
  );
}

/** Cycling pre-token status beneath the GUMMY avatar. */
function StreamingStatus() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(
      () => setI((n) => Math.min(n + 1, STREAM_PHASES.length - 1)),
      750,
    );
    return () => clearInterval(t);
  }, []);
  return (
    <div className="text-muted-foreground flex items-center gap-2 text-sm">
      <span className="bg-primary size-1.5 animate-pulse rounded-full" />
      {STREAM_PHASES[i]}
    </div>
  );
}

/** Collapsible "Memory Used" disclosure (never exposes embeddings/scores). */
function MemoryUsed({ memories }: { memories: string[] }) {
  const [open, setOpen] = useState(false);
  if (memories.length === 0) return null;
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-muted-foreground hover:text-primary inline-flex items-center gap-1.5 text-xs transition-colors"
      >
        <Brain className="size-3.5" />
        Memory Used ({memories.length})
        <ChevronDown
          className={cn("size-3 transition-transform", open && "rotate-180")}
        />
      </button>
      {open ? (
        <ul className="border-primary/20 mt-1.5 space-y-1 border-l pl-3">
          {memories.map((m, i) => (
            <li key={i} className="text-muted-foreground text-xs">
              {m}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function ChatPane({
  activeId,
  agentContext,
  onAgentContextChange,
  onActiveIdChange,
  onOpenHistory,
  onOpenHub,
  initialPrompt = "",
}: {
  activeId: string | null;
  agentContext: string;
  onAgentContextChange: (v: string) => void;
  onActiveIdChange: (id: string) => void;
  onOpenHistory: () => void;
  onOpenHub: () => void;
  initialPrompt?: string;
}) {
  const [value, setValue] = useState(initialPrompt);
  const [pending, setPending] = useState<string | null>(null);
  const [streamText, setStreamText] = useState("");
  const [sending, setSending] = useState(false);
  const [memoriesByMessage, setMemoriesByMessage] = useState<
    Record<string, string[]>
  >({});

  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const atBottomRef = useRef(true);
  const abortRef = useRef<AbortController | null>(null);
  const streamingConvRef = useRef<string | null>(null);
  const mountedRef = useRef(true);
  const qc = useQueryClient();

  // Abort any in-flight stream when the pane unmounts so the SSE reader is
  // released and no setState fires on an unmounted component.
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  // Switching to a *different* conversation while a reply is streaming aborts
  // it and drops the live bubble, so a half-streamed answer never bleeds into
  // another thread. Promoting a brand-new chat (activeId catches up to the one
  // we're streaming into) is excluded.
  useEffect(() => {
    if (
      abortRef.current &&
      streamingConvRef.current &&
      activeId !== streamingConvRef.current
    ) {
      abortRef.current.abort();
      abortRef.current = null;
      streamingConvRef.current = null;
      setPending(null);
      setStreamText("");
      setSending(false);
    }
  }, [activeId]);

  const { data, isLoading, isError } = useMessages(activeId);
  const createConv = useCreateConversation();
  const messages = data?.items ?? [];

  // Auto-scroll while streaming, but only if the user is already at the bottom
  // (so scrolling up to read history is never yanked back down).
  useEffect(() => {
    if (atBottomRef.current) {
      bottomRef.current?.scrollIntoView({
        behavior: sending ? "auto" : "smooth",
      });
    }
  }, [messages.length, streamText, pending, sending]);

  // Diagnostic: log each persisted (server) message when the query resolves.
  useEffect(() => {
    for (const m of data?.items ?? []) logMsg(m.id, m.role, "server");
  }, [data]);

  function onScroll() {
    const el = scrollRef.current;
    if (!el) return;
    atBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }

  async function send() {
    const text = value.trim();
    if (!text || sending) return;
    setValue("");
    setPending(text);
    setStreamText("");
    setSending(true);
    atBottomRef.current = true;
    logMsg("(pending)", "user", "optimistic");

    const controller = new AbortController();
    abortRef.current = controller;

    let id = activeId;
    try {
      if (!id) {
        const conv = await createConv.mutateAsync(
          modeToAgentContext(agentContext),
        );
        id = conv.id;
        streamingConvRef.current = id;
        onActiveIdChange(id);
      } else {
        streamingConvRef.current = id;
      }

      for await (const ev of streamTurn(id, text, controller.signal)) {
        if (ev.type === "delta" && ev.text) {
          setStreamText((prev) => prev + ev.text);
        } else if (ev.type === "done" && ev.assistant_message_id) {
          logMsg(ev.assistant_message_id, "assistant", "stream");
          setMemoriesByMessage((m) => ({
            ...m,
            [ev.assistant_message_id as string]: ev.memories ?? [],
          }));
        }
      }
      // Refetch the persisted messages BEFORE clearing the live bubble so the
      // streamed text is seamlessly replaced (no flicker).
      await qc.invalidateQueries({ queryKey: ["messages", id] });
      // Fire-and-forget: don't block clearing the live bubble on the (slower)
      // conversations-list refetch, or the streamed bubble overlaps the now-
      // persisted message for the duration of that request (temporary duplicate).
      void qc.invalidateQueries({ queryKey: ["conversations"] });
    } catch (err) {
      // Intentional abort (conversation switch / unmount): stay silent — the
      // switch effect or unmount already handled cleanup.
      if (controller.signal.aborted) return;
      // The stream broke mid-flight. Fall back to the non-streaming turn once
      // so the user still gets a persisted reply instead of a dead end.
      try {
        if (!id) throw err;
        await postTurn(id, text);
        await qc.invalidateQueries({ queryKey: ["messages", id] });
        // Fire-and-forget: don't block clearing the live bubble on the (slower)
      // conversations-list refetch, or the streamed bubble overlaps the now-
      // persisted message for the duration of that request (temporary duplicate).
      void qc.invalidateQueries({ queryKey: ["conversations"] });
      } catch {
        toast.error("Couldn't reach GUMMY. Is the backend running?");
        if (mountedRef.current) setValue(text);
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      streamingConvRef.current = null;
      // Skip state writes when aborted (component unmounted or the switch
      // effect already reset the live bubble).
      if (!controller.signal.aborted && mountedRef.current) {
        setPending(null);
        setStreamText("");
        setSending(false);
      }
    }
  }

  const isEmpty = !activeId && !pending && messages.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <div className="flex items-center gap-1.5">
          <button
            onClick={onOpenHistory}
            aria-label="Conversations"
            className="text-muted-foreground hover:bg-accent hover:text-foreground grid size-8 place-items-center rounded-lg lg:hidden"
          >
            <PanelLeft className="size-4" />
          </button>
          <AgentSelect value={agentContext} onChange={onAgentContextChange} />
        </div>
        <button
          onClick={onOpenHub}
          className="text-muted-foreground hover:bg-accent hover:text-foreground inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-sm"
        >
          <PanelRight className="size-4" />
          <span className="hidden sm:inline">Workspace Hub</span>
        </button>
      </div>

      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-4"
      >
        {isEmpty ? (
          <WelcomeScreen onPick={(s) => setValue(s)} />
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-6">
            {isLoading && activeId ? <ChatSkeleton /> : null}
            {isError && activeId ? (
              <p className="text-muted-foreground text-sm">
                Couldn&apos;t load this conversation.
              </p>
            ) : null}
            {messages.map((m, i) => {
              const prevUser =
                m.role === "assistant"
                  ? messages
                      .slice(0, i)
                      .reverse()
                      .find((x) => x.role === "user")
                  : null;
              const agent =
                prevUser != null
                  ? previewRoutedAgents(prevUser.content, agentContext)[0]
                  : null;
              return (
                <MessageBubble
                  key={m.id}
                  role={m.role}
                  content={m.content}
                  footer={
                    m.role === "assistant" ? (
                      <div className="mt-1.5 space-y-0.5">
                        {agent ? <AgentChip label={agent} /> : null}
                        <MemoryUsed memories={memoriesByMessage[m.id] ?? []} />
                      </div>
                    ) : null
                  }
                />
              );
            })}
            {pending ? (
              <>
                <MessageBubble role="user" content={pending} />
                <MessageBubble
                  role="assistant"
                  content={streamText}
                  streaming={streamText.length > 0}
                  status={<StreamingStatus />}
                />
              </>
            ) : null}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="px-4 pb-4">
        <div className="mx-auto max-w-3xl">
          <Composer
            value={value}
            onChange={setValue}
            onSend={send}
            disabled={sending}
          />
        </div>
      </div>
    </div>
  );
}

function WelcomeScreen({ onPick }: { onPick: (s: string) => void }) {
  const { user } = useAuth();
  const { data: profile } = useProfile();
  const topMemories = useSnapshotMemories(3);

  const firstName = useMemo(
    () => greetingName(profile, user),
    [profile, user],
  );

  const greeting = useMemo(() => {
    const h = new Date().getHours();
    return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  }, []);

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center gap-8 py-10 text-center">
      <LivingOrb size={132} state="idle" />
      <div className="space-y-1.5">
        <h2 className="font-heading text-3xl font-semibold tracking-tight">
          {greeting}, {firstName}.
        </h2>
        <p className="text-muted-foreground text-base">
          How can GUMMY help today?
        </p>
      </div>

      <div className="grid w-full grid-cols-2 gap-2.5 sm:grid-cols-3">
        {QUICK_ACTIONS.map(({ icon: Icon, label, prompt }) => (
          <button
            key={label}
            onClick={() => onPick(prompt)}
            className="glass hover:border-primary/40 hover:bg-primary/5 group flex items-center gap-2.5 rounded-xl px-3.5 py-3 text-left text-sm transition-all hover:-translate-y-0.5"
          >
            <span className="bg-primary/10 text-primary grid size-8 shrink-0 place-items-center rounded-lg">
              <Icon className="size-4" />
            </span>
            <span className="font-medium">{label}</span>
          </button>
        ))}
      </div>

      {topMemories.length > 0 ? (
        <div className="glass w-full rounded-2xl p-4 text-left">
          <div className="text-muted-foreground mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide uppercase">
            <Brain className="text-primary size-3.5" />
            Memory Snapshot
          </div>
          <ul className="space-y-1">
            {topMemories.map((m) => (
              <li key={m.id} className="text-sm">
                <span className="text-primary/70">•</span> {m.content}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function ChatSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <div className="bg-muted/60 h-10 w-48 animate-pulse rounded-2xl" />
      </div>
      <div className="flex gap-3">
        <div className="bg-muted/60 size-7 shrink-0 animate-pulse rounded-full" />
        <div className="flex-1 space-y-2">
          <div className="bg-muted/60 h-3 w-24 animate-pulse rounded" />
          <div className="bg-muted/60 h-3 w-full animate-pulse rounded" />
          <div className="bg-muted/60 h-3 w-4/5 animate-pulse rounded" />
        </div>
      </div>
    </div>
  );
}
