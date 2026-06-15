"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { LivingOrb } from "@/components/brand/LivingOrb";
import { Composer } from "@/components/workspace/Composer";
import { MessageBubble } from "@/components/workspace/MessageBubble";
import {
  useCreateConversation,
  useMessages,
  useSendTurn,
} from "@/lib/hooks/useChat";
import {
  AGENT_MODES,
  modeToAgentContext,
  previewRoutedAgents,
} from "@/lib/chat/routing";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "What can you help me with?",
  "Remember that I prefer concise answers",
  "Help me plan my week",
  "What do you know about me?",
];

export function ChatPane({
  activeId,
  agentContext,
  onAgentContextChange,
  onActiveIdChange,
  initialPrompt = "",
}: {
  activeId: string | null;
  agentContext: string;
  onAgentContextChange: (v: string) => void;
  onActiveIdChange: (id: string) => void;
  initialPrompt?: string;
}) {
  const [value, setValue] = useState(initialPrompt);
  const [pending, setPending] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data, isLoading, isError } = useMessages(activeId);
  const createConv = useCreateConversation();
  const sendTurn = useSendTurn();

  const messages = data?.items ?? [];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, pending]);

  async function send() {
    const text = value.trim();
    if (!text || sending) return;
    setValue("");
    setPending(text);
    setSending(true);
    try {
      let id = activeId;
      if (!id) {
        const conv = await createConv.mutateAsync(
          modeToAgentContext(agentContext),
        );
        id = conv.id;
        onActiveIdChange(id);
      }
      await sendTurn.mutateAsync({ conversationId: id, message: text });
    } catch {
      toast.error("Couldn't reach GUMMY. Is the backend running?");
      setValue(text);
    } finally {
      setPending(null);
      setSending(false);
    }
  }

  const isEmpty = !activeId && !pending && messages.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Agent bar */}
      <div className="flex items-center justify-between gap-3 border-b border-white/10 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground text-xs">Agent</span>
          <select
            value={agentContext}
            onChange={(e) => onAgentContextChange(e.target.value)}
            className="border-input focus-visible:border-ring focus-visible:ring-ring/50 h-8 rounded-lg border bg-transparent px-2 text-sm outline-none focus-visible:ring-2"
          >
            {AGENT_MODES.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
        </div>
        <span className="text-muted-foreground hidden text-xs sm:inline">
          {agentContext === "auto"
            ? "GUMMY selects agents automatically"
            : messages.length > 0
              ? `${messages.length} messages`
              : "New conversation"}
        </span>
      </div>

      {/* Messages */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6">
        {isEmpty ? (
          <WelcomeState
            onPick={(s) => {
              setValue(s);
            }}
          />
        ) : (
          <div className="mx-auto flex max-w-2xl flex-col gap-6">
            {isLoading && activeId ? (
              <p className="text-muted-foreground text-sm">Loading…</p>
            ) : null}
            {isError && activeId ? (
              <p className="text-muted-foreground text-sm">
                Couldn&apos;t load this conversation.
              </p>
            ) : null}
            {messages.map((m) => (
              <MessageBubble key={m.id} role={m.role} content={m.content} />
            ))}
            {pending ? (
              <>
                <MessageBubble role="user" content={pending} />
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-muted-foreground text-xs">
                    Active Agents
                  </span>
                  {previewRoutedAgents(pending, agentContext).map((label) => (
                    <span
                      key={label}
                      className="border-primary/30 bg-primary/10 text-primary rounded-full border px-2 py-0.5 text-[11px] font-medium"
                    >
                      {label}
                    </span>
                  ))}
                </div>
                <MessageBubble role="assistant" content="" thinking />
              </>
            ) : null}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="border-t border-white/10 px-4 py-3">
        <div className="mx-auto max-w-2xl">
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

function WelcomeState({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-6 py-10 text-center">
      <LivingOrb size={120} state="idle" />
      <div>
        <h2 className="font-heading text-2xl font-semibold tracking-tight">
          How can I help?
        </h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Ask anything. GUMMY remembers what matters.
        </p>
      </div>
      <div className="flex flex-wrap justify-center gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className={cn(
              "glass hover:border-primary/40 rounded-full px-3.5 py-1.5 text-sm transition-colors",
            )}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
