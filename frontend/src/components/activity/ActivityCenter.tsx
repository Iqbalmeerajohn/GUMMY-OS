"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  Activity,
  CheckCircle2,
  CircleSlash,
  Clock,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  fetchCapabilities,
  listActivity,
  type ActivityItem,
  type ApprovalTier,
  type CapabilityItem,
} from "@/lib/api/resources";
import { cn } from "@/lib/utils";

/**
 * Activity — what GUMMY has actually done, and what it is able to do.
 *
 * Every tool call has always been written to an audit row with its tier,
 * decision and outcome. Nothing read it: the only access was per-run, which
 * required already knowing which turn you cared about. This is the other
 * direction — newest first, across everything — so the trail is something a
 * person can look at rather than a table only the orchestrator writes to.
 *
 * The Capabilities tab is deliberately generated from the live catalog rather
 * than written down. A hand-maintained list of "what GUMMY can do" is wrong
 * the first time a tool is added, and the catalog is fixed at startup, so the
 * exact answer is knowable. It also surfaces the gap that matters most: the
 * machine-facing tools exist but refuse every path until a workspace is
 * configured, which makes them present but unusable — worth saying out loud
 * rather than letting someone discover it mid-conversation.
 */

const TIER_DOT: Record<ApprovalTier, string> = {
  green: "bg-emerald-400",
  yellow: "bg-amber-400",
  red: "bg-red-400",
};

const TIER_NOTE: Record<ApprovalTier, string> = {
  green: "runs immediately",
  yellow: "needs your approval",
  red: "needs approval every time",
};

function StatusIcon({ status }: { status: string }) {
  if (status === "succeeded")
    return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />;
  if (status === "failed")
    return <XCircle className="h-3.5 w-3.5 text-red-400" />;
  return <CircleSlash className="text-muted-foreground h-3.5 w-3.5" />;
}

function ago(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

function Feed() {
  const { data, isLoading } = useQuery({
    queryKey: ["activity"],
    queryFn: () => listActivity(50),
    refetchInterval: 15_000,
  });

  if (isLoading) {
    return (
      <div className="space-y-2 p-1">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </div>
    );
  }

  const items = data ?? [];
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
        <Activity className="text-muted-foreground/40 h-10 w-10" />
        <p className="text-sm font-medium">Nothing yet</p>
        <p className="text-muted-foreground max-w-xs text-xs leading-relaxed">
          Every tool GUMMY runs is recorded here with its tier and outcome. Ask
          it to do something that needs a tool.
        </p>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-white/5">
      {items.map((item: ActivityItem) => (
        <li key={item.id} className="flex items-start gap-3 py-2.5">
          <span
            className={cn(
              "mt-1.5 h-2 w-2 shrink-0 rounded-full",
              TIER_DOT[item.tier],
            )}
            title={TIER_NOTE[item.tier]}
          />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="truncate font-mono text-xs font-medium">
                {item.tool_key}
              </span>
              <StatusIcon status={item.status} />
            </div>
            <p className="text-muted-foreground mt-0.5 text-[11px]">
              {item.agent_key} · {item.decision} · {ago(item.created_at)}
            </p>
            {/* The reason a call was blocked or deferred is the most useful
                thing in the row, so it is shown rather than hidden. */}
            {item.error || item.decision_reason ? (
              <p className="text-muted-foreground/80 mt-1 text-[11px] italic">
                {item.error ?? item.decision_reason}
              </p>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}

function Capabilities() {
  const { data, isLoading } = useQuery({
    queryKey: ["capabilities"],
    queryFn: fetchCapabilities,
    // The catalog is sealed at startup, so this cannot change while the page
    // is open. Fetch once.
    staleTime: Infinity,
  });

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!data) return null;

  const grouped = data.tools.reduce<Record<string, CapabilityItem[]>>(
    (acc, tool) => {
      (acc[tool.category] ??= []).push(tool);
      return acc;
    },
    {},
  );

  return (
    <div className="space-y-4 p-1">
      <section className="grid grid-cols-3 gap-2 text-center">
        {[
          { label: "Tools", value: data.total },
          { label: "Runnable", value: data.executable },
          {
            label: "Need approval",
            value: (data.by_tier.yellow ?? 0) + (data.by_tier.red ?? 0),
          },
        ].map((stat) => (
          <div
            key={stat.label}
            className="rounded-lg border border-white/5 p-3"
          >
            <p className="text-xl font-semibold">{stat.value}</p>
            <p className="text-muted-foreground text-[11px]">{stat.label}</p>
          </div>
        ))}
      </section>

      {/* The honest caveat: these tools exist but do nothing without a root. */}
      {!data.workspace_configured ? (
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs leading-relaxed text-amber-200">
          No workspace is configured, so the git, file and shell tools refuse
          every path. Set{" "}
          <code className="font-mono">GUMMY_WORKSPACE_ROOTS</code> in{" "}
          <code className="font-mono">backend/.env</code> to use them.
        </p>
      ) : (
        <p className="text-muted-foreground text-[11px]">
          Workspace: {data.workspace_roots.join(", ")}
        </p>
      )}

      {Object.entries(grouped)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([category, tools]) => (
          <section key={category}>
            <h3 className="text-muted-foreground mb-1.5 text-[11px] font-semibold tracking-wide uppercase">
              {category}
            </h3>
            <ul className="space-y-1.5">
              {tools.map((tool) => (
                <li key={tool.key} className="flex items-start gap-2.5">
                  <span
                    className={cn(
                      "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                      TIER_DOT[tool.tier],
                    )}
                    title={TIER_NOTE[tool.tier]}
                  />
                  <div className="min-w-0">
                    <p className="font-mono text-xs">
                      {tool.key}
                      {!tool.executable ? (
                        <span className="text-muted-foreground ml-1.5 not-italic">
                          (declared, not wired up)
                        </span>
                      ) : null}
                    </p>
                    <p className="text-muted-foreground line-clamp-2 text-[11px]">
                      {tool.description}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
    </div>
  );
}

export function ActivityCenter() {
  const [tab, setTab] = useState<"feed" | "capabilities">("feed");

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex gap-1">
        <Button
          size="sm"
          variant={tab === "feed" ? "secondary" : "ghost"}
          onClick={() => setTab("feed")}
        >
          <Clock className="mr-1 h-3.5 w-3.5" />
          Recent
        </Button>
        <Button
          size="sm"
          variant={tab === "capabilities" ? "secondary" : "ghost"}
          onClick={() => setTab("capabilities")}
        >
          <Activity className="mr-1 h-3.5 w-3.5" />
          What it can do
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === "feed" ? <Feed /> : <Capabilities />}
      </div>
    </div>
  );
}
