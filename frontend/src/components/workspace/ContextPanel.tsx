"use client";

import Link from "next/link";
import { Brain, FileText, Layers, Target } from "lucide-react";

import { StatusBadge } from "@/components/feature/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useActiveGoals, useRecentMemories } from "@/lib/hooks/useDashboard";
import { AGENT_CONTEXTS } from "@/lib/chat/agents";

/** Right rail — what GUMMY is working with: memory, goals, files, context. */
export function ContextPanel({ agentContext }: { agentContext: string }) {
  const agentLabel =
    AGENT_CONTEXTS.find((a) => a.value === agentContext)?.label ?? "General";

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto p-3">
      <ContextPreview agentLabel={agentLabel} />
      <MemoryPreview />
      <GoalsPreview />
      <FilesPreview />
    </div>
  );
}

function Panel({
  icon: Icon,
  title,
  action,
  children,
}: {
  icon: typeof Brain;
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="glass rounded-2xl p-4">
      <div className="mb-3 flex items-center justify-between">
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

function ContextPreview({ agentLabel }: { agentLabel: string }) {
  return (
    <Panel icon={Layers} title="Context">
      <dl className="space-y-1.5 text-sm">
        <div className="flex items-center justify-between">
          <dt className="text-muted-foreground text-xs">Active agent</dt>
          <dd className="font-medium">{agentLabel}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-muted-foreground text-xs">Memory</dt>
          <dd className="font-medium">In the loop</dd>
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
    </Panel>
  );
}

function FilesPreview() {
  return (
    <Panel
      icon={FileText}
      title="Files"
      action={<StatusBadge status="planned" />}
    >
      <p className="text-muted-foreground text-xs text-balance">
        Documents and attachments will live here.
      </p>
    </Panel>
  );
}
