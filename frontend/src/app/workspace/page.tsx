"use client";

import { Suspense, useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import { X } from "lucide-react";

import { ChatPane } from "@/components/workspace/ChatPane";
import { ContextPanel } from "@/components/workspace/ContextPanel";
import { HistoryRail } from "@/components/workspace/HistoryRail";
import { analytics, AnalyticsEvent } from "@/lib/analytics";

/** A slide-over sheet (left = history on mobile, right = the Workspace Hub). */
function Sheet({
  open,
  side,
  title,
  onClose,
  children,
}: {
  open: boolean;
  side: "left" | "right";
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40">
      <button
        aria-label="Close panel"
        onClick={onClose}
        className="absolute inset-0 bg-black/50"
      />
      <div
        className={`bg-background absolute inset-y-0 flex w-96 max-w-[90%] flex-col border-white/10 ${
          side === "left" ? "left-0 border-r" : "right-0 border-l"
        }`}
      >
        <div className="flex items-center justify-between border-b border-white/10 px-3 py-2.5">
          <span className="text-sm font-medium">{title}</span>
          <button
            aria-label="Close"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1">{children}</div>
      </div>
    </div>
  );
}

function Workspace() {
  const params = useSearchParams();
  const initialPrompt = params.get("prompt") ?? "";
  // Deep-link target from unified search (`/workspace?c=<id>`).
  const [activeId, setActiveId] = useState<string | null>(params.get("c"));
  const [agentContext, setAgentContext] = useState("auto");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [hubOpen, setHubOpen] = useState(false);

  // Workspace entry — fires once per mount (deep-linked or fresh).
  useEffect(() => {
    analytics.track(AnalyticsEvent.WorkspaceOpened, {
      deep_linked: Boolean(params.get("c")),
    });
    // Mount-only: a new visit to the workspace is a new mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function selectConversation(id: string) {
    analytics.track(AnalyticsEvent.ConversationOpened, { conversation_id: id });
    setActiveId(id);
    setHistoryOpen(false);
  }

  function changeAgentContext(value: string) {
    if (value !== agentContext) {
      analytics.track(AnalyticsEvent.AgentSelected, { agent_context: value });
    }
    setAgentContext(value);
  }

  // "New" resets to the welcome state — the conversation is created lazily on
  // the first message (in ChatPane.send). Creating it eagerly produced an empty
  // conversation with activeId set, which suppressed the welcome screen (the
  // intermittent "blank workspace" bug).
  function newConversation() {
    setActiveId(null);
    setHistoryOpen(false);
  }

  return (
    <div className="flex h-full min-h-0">
      {/* History rail — desktop (~20%). */}
      <aside className="hidden w-64 shrink-0 border-r border-white/10 lg:block">
        <HistoryRail
          activeId={activeId}
          onSelect={selectConversation}
          onNew={newConversation}
        />
      </aside>

      {/* Chat — dominant (~80%). */}
      <div className="flex min-w-0 flex-1 flex-col">
        <ChatPane
          activeId={activeId}
          agentContext={agentContext}
          onAgentContextChange={changeAgentContext}
          onActiveIdChange={setActiveId}
          onOpenHistory={() => setHistoryOpen(true)}
          onOpenHub={() => setHubOpen(true)}
          initialPrompt={initialPrompt}
        />
      </div>

      {/* History — mobile slide-over. */}
      <Sheet
        open={historyOpen}
        side="left"
        title="Conversations"
        onClose={() => setHistoryOpen(false)}
      >
        <HistoryRail
          activeId={activeId}
          onSelect={selectConversation}
          onNew={newConversation}
        />
      </Sheet>

      {/* Workspace Hub — slide-over (desktop + mobile). */}
      <Sheet
        open={hubOpen}
        side="right"
        title="Workspace Hub"
        onClose={() => setHubOpen(false)}
      >
        <ContextPanel agentContext={agentContext} />
      </Sheet>
    </div>
  );
}

export default function WorkspacePage() {
  return (
    <Suspense fallback={null}>
      <Workspace />
    </Suspense>
  );
}
