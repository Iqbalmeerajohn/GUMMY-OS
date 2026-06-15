"use client";

import Link from "next/link";
import {
  Brain,
  FileText,
  Layers,
  Mic,
  Plug,
  Sparkles,
  Target,
  Workflow,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";

import { StatusBadge } from "@/components/feature/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useActiveGoals, useRecentMemories } from "@/lib/hooks/useDashboard";
import { AGENT_MODES } from "@/lib/chat/routing";

/**
 * Right rail — what GUMMY is working with. Memory + Goals are live; Files,
 * Workflows, Tools, Automation, Voice, and Learning Mode are architecture +
 * UI extension points (no functionality yet).
 */
export function ContextPanel({ agentContext }: { agentContext: string }) {
  const agentLabel =
    AGENT_MODES.find((a) => a.value === agentContext)?.label ?? "Auto";

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto p-3">
      <ContextPreview agentLabel={agentLabel} />
      <MemoryPreview />
      <GoalsPreview />
      <FilesSection />
      <WorkflowsSection />
      <ToolsSection />
      <AutomationSection />
      <VoiceSection />
      <LearningModeSection />
    </div>
  );
}

function Panel({
  icon: Icon,
  title,
  action,
  children,
}: {
  icon: LucideIcon;
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="glass rounded-2xl p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-xs font-medium tracking-[0.12em] uppercase">
          <Icon className="text-primary size-3.5" />
          {title}
        </span>
        {action}
      </div>
      {children}
    </section>
  );
}

/** A row of disabled action chips (extension points). */
function Actions({ items }: { items: string[] }) {
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {items.map((label) => (
        <button
          key={label}
          onClick={() => toast.info(`${label} is planned — coming soon.`)}
          className="border-border/60 text-muted-foreground hover:text-foreground rounded-full border px-2.5 py-1 text-xs transition-colors"
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function ContextPreview({ agentLabel }: { agentLabel: string }) {
  return (
    <Panel icon={Layers} title="Context">
      <dl className="space-y-1.5">
        <div className="flex items-center justify-between">
          <dt className="text-muted-foreground text-xs">Active agent</dt>
          <dd className="text-sm font-medium">{agentLabel}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-muted-foreground text-xs">Memory</dt>
          <dd className="text-sm font-medium">In the loop</dd>
        </div>
      </dl>
    </Panel>
  );
}

function MemoryPreview() {
  const { data, isLoading, isError } = useRecentMemories();
  const items = data?.items ?? [];
  return (
    <Panel
      icon={Brain}
      title="Memory"
      action={
        <Link
          href="/dashboard"
          className="text-muted-foreground text-xs hover:underline"
        >
          View
        </Link>
      }
    >
      {isLoading ? (
        <Skeleton className="h-12 w-full rounded-lg" />
      ) : isError || items.length === 0 ? (
        <p className="text-muted-foreground text-xs">Nothing remembered yet.</p>
      ) : (
        <ul className="space-y-1.5">
          {items.slice(0, 3).map((m) => (
            <li key={m.id} className="flex items-start gap-1.5">
              <Badge variant="secondary" className="shrink-0 text-[9px]">
                {m.category}
              </Badge>
              <span className="line-clamp-1 text-xs">{m.content}</span>
            </li>
          ))}
        </ul>
      )}
      <Actions items={["Search", "Manage"]} />
    </Panel>
  );
}

function GoalsPreview() {
  const { data, isLoading, isError } = useActiveGoals();
  const items = data?.items ?? [];
  return (
    <Panel icon={Target} title="Goals">
      {isLoading ? (
        <Skeleton className="h-10 w-full rounded-lg" />
      ) : isError || items.length === 0 ? (
        <p className="text-muted-foreground text-xs">No active goals.</p>
      ) : (
        <ul className="space-y-1.5">
          {items.slice(0, 3).map((g) => (
            <li key={g.id} className="line-clamp-1 text-xs font-medium">
              {g.title}
            </li>
          ))}
        </ul>
      )}
      <Actions items={["Create", "Progress"]} />
    </Panel>
  );
}

function FilesSection() {
  return (
    <Panel
      icon={FileText}
      title="Files"
      action={<StatusBadge status="planned" />}
    >
      <p className="text-muted-foreground text-xs text-balance">
        Documents and attachments will live here.
      </p>
      <Actions items={["Upload", "Browse", "Search"]} />
    </Panel>
  );
}

function WorkflowsSection() {
  return (
    <Panel
      icon={Workflow}
      title="Workflows"
      action={<StatusBadge status="planned" />}
    >
      <dl className="space-y-1.5">
        <div className="flex items-center justify-between">
          <dt className="text-muted-foreground text-xs">Active</dt>
          <dd className="text-xs">0</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-muted-foreground text-xs">Pending</dt>
          <dd className="text-xs">0</dd>
        </div>
      </dl>
    </Panel>
  );
}

function ToolsSection() {
  return (
    <Panel icon={Plug} title="Tools" action={<StatusBadge status="planned" />}>
      <p className="text-muted-foreground text-xs text-balance">
        Connected integrations (calendars, email, docs).
      </p>
    </Panel>
  );
}

function AutomationSection() {
  return (
    <Panel
      icon={Zap}
      title="Automation"
      action={<StatusBadge status="planned" />}
    >
      <p className="text-muted-foreground text-xs">Running flows: 0</p>
    </Panel>
  );
}

function VoiceSection() {
  return (
    <Panel
      icon={Mic}
      title="Voice"
      action={<StatusBadge status="researching" />}
    >
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground text-xs">Status</span>
        <span className="text-xs font-medium">Off</span>
      </div>
    </Panel>
  );
}

function LearningModeSection() {
  return (
    <Panel
      icon={Sparkles}
      title="Learning Mode"
      action={<StatusBadge status="researching" />}
    >
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground text-xs">
          Learn my workflows
        </span>
        <span className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-[10px]">
          Disabled
        </span>
      </div>
    </Panel>
  );
}
