"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import {
  Brain,
  FileText,
  MessagesSquare,
  Plus,
  Search,
  Settings,
  Target,
  Users,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";

import { LivingOrb } from "@/components/brand/LivingOrb";
import { AgentDirectory } from "@/components/agents/AgentDirectory";
import { AutomationsCenter } from "@/components/automations/AutomationsCenter";
import { FilesCenter } from "@/components/files/FilesCenter";
import { GoalsCenter } from "@/components/goals/GoalsCenter";
import { MemoryCenter } from "@/components/memory/MemoryCenter";
import { SettingsPanel } from "@/components/profile/SettingsPanel";
import { SearchPanel } from "@/components/search/SearchPanel";
import { ChatPane } from "@/components/workspace/ChatPane";
import { HistoryRail } from "@/components/workspace/HistoryRail";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { analytics, AnalyticsEvent } from "@/lib/analytics";
import { cn } from "@/lib/utils";

type PanelId =
  | "history"
  | "search"
  | "memory"
  | "goals"
  | "files"
  | "agents"
  | "automations"
  | "settings";

/** Panels wide enough to need it get a roomier sheet; the rest stay narrow. */
const WIDE: ReadonlySet<PanelId> = new Set(["memory", "goals", "files"]);

const RAIL: { id: PanelId; label: string; icon: LucideIcon }[] = [
  { id: "history", label: "Chats", icon: MessagesSquare },
  { id: "search", label: "Search", icon: Search },
  { id: "memory", label: "Memory", icon: Brain },
  { id: "goals", label: "Goals", icon: Target },
  { id: "files", label: "Files", icon: FileText },
  { id: "agents", label: "Agents", icon: Users },
  { id: "automations", label: "Automations", icon: Zap },
];

const TITLES: Record<PanelId, string> = {
  history: "Chats",
  search: "Search",
  memory: "Memory",
  goals: "Goals",
  files: "Files",
  agents: "Agents",
  automations: "Automations",
  settings: "Settings",
};

/**
 * GUMMY's only interface: a chat surface, with everything else one icon away.
 *
 * There are no other pages. Memory, Goals, Files, Agents, Search, and Settings
 * are slide-over panels over the same conversation, so context is never lost to
 * a navigation — which is the whole point of an assistant that remembers.
 */
function Shell() {
  const params = useSearchParams();
  const initialPrompt = params.get("prompt") ?? "";
  const [activeId, setActiveId] = useState<string | null>(params.get("c"));
  const [agentContext, setAgentContext] = useState("auto");
  const [panel, setPanel] = useState<PanelId | null>(null);

  useEffect(() => {
    analytics.track(AnalyticsEvent.WorkspaceOpened, {
      deep_linked: Boolean(params.get("c")),
    });
    // Mount-only: a new visit is a new mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const close = useCallback(() => setPanel(null), []);

  // Esc closes the open panel; ⌘/Ctrl+K jumps straight to search.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setPanel(null);
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setPanel((p) => (p === "search" ? null : "search"));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const openConversation = useCallback((id: string) => {
    analytics.track(AnalyticsEvent.ConversationOpened, { conversation_id: id });
    setActiveId(id);
    setPanel(null);
  }, []);

  // "New" resets to the welcome state — the conversation is created lazily on
  // the first message (in ChatPane.send).
  const newConversation = useCallback(() => {
    setActiveId(null);
    setPanel(null);
  }, []);

  function changeAgentContext(value: string) {
    if (value !== agentContext) {
      analytics.track(AnalyticsEvent.AgentSelected, { agent_context: value });
    }
    setAgentContext(value);
  }

  return (
    <div className="flex h-[100svh] min-h-0">
      <nav
        aria-label="GUMMY"
        className="glass z-30 flex w-14 shrink-0 flex-col items-center gap-1 border-r border-white/10 py-3"
      >
        <button
          onClick={newConversation}
          aria-label="New chat"
          className="relative mb-1 grid size-10 place-items-center"
        >
          <LivingOrb size={30} state="idle" />
          <span className="bg-primary text-primary-foreground absolute -right-0.5 -bottom-0.5 grid size-4 place-items-center rounded-full">
            <Plus className="size-2.5" />
          </span>
        </button>

        {RAIL.map((item) => (
          <RailButton
            key={item.id}
            {...item}
            active={panel === item.id}
            onClick={() => setPanel((p) => (p === item.id ? null : item.id))}
          />
        ))}

        <div className="flex-1" />
        <RailButton
          id="settings"
          label="Settings"
          icon={Settings}
          active={panel === "settings"}
          onClick={() =>
            setPanel((p) => (p === "settings" ? null : "settings"))
          }
        />
      </nav>

      <main className="flex min-w-0 flex-1 flex-col">
        <ChatPane
          activeId={activeId}
          agentContext={agentContext}
          onAgentContextChange={changeAgentContext}
          onActiveIdChange={setActiveId}
          onOpenHistory={() => setPanel("history")}
          onOpenHub={() => setPanel("memory")}
          initialPrompt={initialPrompt}
        />
      </main>

      <SlideOver
        panel={panel}
        onClose={close}
        activeId={activeId}
        onSelectConversation={openConversation}
        onNewConversation={newConversation}
        onOpenPanel={setPanel}
      />
    </div>
  );
}

function RailButton({
  label,
  icon: Icon,
  active,
  onClick,
}: {
  id: PanelId;
  label: string;
  icon: LucideIcon;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            onClick={onClick}
            aria-label={label}
            aria-pressed={active}
            className={cn(
              "grid size-10 place-items-center rounded-xl transition-colors",
              active
                ? "bg-primary/15 text-primary"
                : "text-muted-foreground hover:bg-accent hover:text-foreground",
            )}
          >
            <Icon className="size-5" />
          </button>
        }
      />
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}

/** The one sheet every panel renders into, anchored beside the rail. */
function SlideOver({
  panel,
  onClose,
  activeId,
  onSelectConversation,
  onNewConversation,
  onOpenPanel,
}: {
  panel: PanelId | null;
  onClose: () => void;
  activeId: string | null;
  onSelectConversation: (id: string) => void;
  onNewConversation: () => void;
  onOpenPanel: (p: PanelId) => void;
}) {
  return (
    <AnimatePresence>
      {panel ? (
        <>
          <motion.button
            key="scrim"
            aria-label="Close panel"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-30 bg-black/50"
          />
          <motion.aside
            key="panel"
            initial={{ x: -24, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: -24, opacity: 0 }}
            transition={{ type: "spring", stiffness: 420, damping: 38 }}
            className={cn(
              "bg-background fixed inset-y-0 left-14 z-40 flex max-w-[calc(100vw-3.5rem)] flex-col border-r border-white/10",
              WIDE.has(panel) ? "w-[42rem]" : "w-[24rem]",
            )}
          >
            <header className="flex items-center justify-between border-b border-white/10 px-4 py-2.5">
              <span className="text-sm font-medium">{TITLES[panel]}</span>
              <button
                aria-label="Close"
                onClick={onClose}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto">
              {panel === "history" ? (
                <HistoryRail
                  activeId={activeId}
                  onSelect={onSelectConversation}
                  onNew={onNewConversation}
                />
              ) : panel === "search" ? (
                <SearchPanel
                  onOpenConversation={onSelectConversation}
                  onOpenMemories={() => onOpenPanel("memory")}
                />
              ) : panel === "memory" ? (
                <MemoryCenter />
              ) : panel === "goals" ? (
                <GoalsCenter />
              ) : panel === "files" ? (
                <FilesCenter />
              ) : panel === "agents" ? (
                <AgentDirectory />
              ) : panel === "automations" ? (
                <AutomationsCenter />
              ) : (
                <SettingsPanel />
              )}
            </div>
          </motion.aside>
        </>
      ) : null}
    </AnimatePresence>
  );
}

export function GummyShell() {
  return (
    <Suspense fallback={null}>
      <Shell />
    </Suspense>
  );
}
