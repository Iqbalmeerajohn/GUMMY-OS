"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { PanelLeft, PanelRight, X } from "lucide-react";

import { ChatPane } from "@/components/workspace/ChatPane";
import { ContextPanel } from "@/components/workspace/ContextPanel";
import { HistoryRail } from "@/components/workspace/HistoryRail";
import { useCreateConversation } from "@/lib/hooks/useChat";

type MobilePanel = "history" | "context" | null;

function Workspace() {
  const initialPrompt = useSearchParams().get("prompt") ?? "";
  const [activeId, setActiveId] = useState<string | null>(null);
  const [agentContext, setAgentContext] = useState("general");
  const [panel, setPanel] = useState<MobilePanel>(null);
  const createConv = useCreateConversation();

  function selectConversation(id: string) {
    setActiveId(id);
    setPanel(null);
  }

  async function newConversation() {
    setPanel(null);
    const conv = await createConv.mutateAsync(agentContext);
    setActiveId(conv.id);
  }

  return (
    <div className="flex h-full min-h-0">
      {/* History — desktop */}
      <aside className="hidden w-72 shrink-0 border-r border-white/10 lg:block">
        <HistoryRail
          activeId={activeId}
          onSelect={selectConversation}
          onNew={newConversation}
        />
      </aside>

      {/* Center */}
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between gap-2 border-b border-white/10 px-3 py-2 xl:hidden">
          <button
            onClick={() => setPanel("history")}
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm lg:hidden"
          >
            <PanelLeft className="size-4" /> History
          </button>
          <span className="lg:hidden" />
          <button
            onClick={() => setPanel("context")}
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm"
          >
            Context <PanelRight className="size-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1">
          <ChatPane
            activeId={activeId}
            agentContext={agentContext}
            onAgentContextChange={setAgentContext}
            onActiveIdChange={setActiveId}
            initialPrompt={initialPrompt}
          />
        </div>
      </div>

      {/* Context — desktop */}
      <aside className="hidden w-80 shrink-0 border-l border-white/10 xl:block">
        <ContextPanel agentContext={agentContext} />
      </aside>

      {/* Mobile overlays */}
      {panel ? (
        <div className="fixed inset-0 z-40 xl:hidden">
          <button
            aria-label="Close panel"
            onClick={() => setPanel(null)}
            className="absolute inset-0 bg-black/50"
          />
          <div
            className={`bg-background absolute inset-y-0 w-80 max-w-[85%] border-white/10 ${
              panel === "history" ? "left-0 border-r" : "right-0 border-l"
            }`}
          >
            <div className="flex items-center justify-between border-b border-white/10 px-3 py-2">
              <span className="text-sm font-medium">
                {panel === "history" ? "Conversations" : "Context"}
              </span>
              <button
                aria-label="Close"
                onClick={() => setPanel(null)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            </div>
            <div className="h-[calc(100%-2.5rem)]">
              {panel === "history" ? (
                <HistoryRail
                  activeId={activeId}
                  onSelect={selectConversation}
                  onNew={newConversation}
                />
              ) : (
                <ContextPanel agentContext={agentContext} />
              )}
            </div>
          </div>
        </div>
      ) : null}
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
