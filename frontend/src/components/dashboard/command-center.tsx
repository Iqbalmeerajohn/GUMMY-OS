"use client";

import Link from "next/link";
import { ArrowRight, Target } from "lucide-react";

import { StatusBadge } from "@/components/feature/StatusBadge";
import { useUpdates } from "@/components/updates/UpdatesProvider";
import { useActiveGoals } from "@/lib/hooks/useDashboard";
import {
  agentStatusLabel,
  getActiveAgents,
  getCapabilityMap,
  getReleased,
} from "@/config/registry";
import { getIcon } from "@/lib/icons";

function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="glass elevation-2 rounded-2xl p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-muted-foreground text-xs font-medium tracking-[0.15em] uppercase">
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/** TODAY'S FOCUS — leads with the user's real top active goal when one exists,
 *  falling back to onboarding guidance for brand-new accounts. */
export function TodaysFocus() {
  const { data, isLoading } = useActiveGoals();
  const goals = data?.items ?? [];
  const topGoal = goals[0] ?? null;
  const goalTitle = topGoal?.title ?? "Set your first goal";

  const nextStep = topGoal
    ? "Open the workspace and ask GUMMY to help you make progress."
    : "Tell GUMMY what you're working toward — it'll track it for you.";

  return (
    <Section title="Today's Focus">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="border-border/50 bg-background/40 rounded-xl border p-4">
          <div className="text-primary flex items-center gap-2 text-sm font-medium">
            <Target className="size-4" />
            Current Goal
          </div>
          <p className="mt-2 line-clamp-2 text-sm">
            {isLoading ? "Loading…" : goalTitle}
          </p>
        </div>
        <div className="border-border/50 bg-background/40 rounded-xl border p-4">
          <span className="text-muted-foreground text-xs">Active goals</span>
          <p className="mt-2 text-2xl leading-none font-semibold tabular-nums">
            {isLoading ? "—" : goals.length}
          </p>
          <p className="text-muted-foreground mt-1.5 text-xs">
            {goals.length === 0 ? "None tracked yet" : "Being tracked by GUMMY"}
          </p>
        </div>
        <div className="border-border/50 bg-background/40 rounded-xl border p-4">
          <span className="text-muted-foreground text-xs">
            Suggested Next Step
          </span>
          <p className="mt-2 text-sm">{nextStep}</p>
        </div>
      </div>
    </Section>
  );
}

/** ACTIVE AGENTS — from the registry. */
export function ActiveAgents() {
  const agents = getActiveAgents();
  return (
    <Section
      title="Active Agents"
      action={
        <Link
          href="/agents"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
        >
          All agents <ArrowRight className="size-3" />
        </Link>
      }
    >
      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map((a) => {
          const Icon = getIcon(a.icon);
          return (
            <div
              key={a.id}
              className="border-border/50 bg-background/40 flex items-start gap-3 rounded-xl border p-3.5"
            >
              <Icon className="text-primary mt-0.5 size-5 shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">
                    {a.title}
                  </span>
                  <StatusBadge
                    status={a.status}
                    label={agentStatusLabel(a.status)}
                  />
                </div>
                <p className="text-muted-foreground mt-1 line-clamp-2 text-xs">
                  {a.description}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </Section>
  );
}

/** CAPABILITY MAP — from the registry. */
export function CapabilityMap() {
  const caps = getCapabilityMap();
  return (
    <Section title="Capability Map">
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        {caps.map((c) => {
          const Icon = getIcon(c.icon);
          return (
            <div
              key={c.id}
              className="border-border/50 bg-background/40 flex flex-col gap-2 rounded-xl border p-3.5"
            >
              <Icon className="text-primary size-5" />
              <span className="text-sm font-medium">{c.title}</span>
              <StatusBadge status={c.status} className="self-start" />
            </div>
          );
        })}
      </div>
    </Section>
  );
}

/** WHAT'S NEW — latest releases from the registry. */
export function WhatsNewWidget() {
  const released = getReleased().slice(0, 3);
  const { updateAvailable, openModal } = useUpdates();
  return (
    <Section
      title="What's New"
      action={
        <Link
          href="/updates"
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
        >
          All updates <ArrowRight className="size-3" />
        </Link>
      }
    >
      {updateAvailable ? (
        <button
          onClick={openModal}
          className="border-primary/30 bg-primary/10 hover:bg-primary/15 mb-3 flex w-full items-center justify-between rounded-xl border px-4 py-2.5 text-left text-sm transition-colors"
        >
          <span className="font-medium">GUMMY learned something new</span>
          <ArrowRight className="size-4" />
        </button>
      ) : null}
      <ul className="space-y-2.5">
        {released.map((r) => (
          <li
            key={r.id}
            className="border-border/50 bg-background/40 flex items-center justify-between gap-2 rounded-lg border p-2.5"
          >
            <span className="text-sm font-medium">{r.title}</span>
            <span className="text-muted-foreground text-xs">
              {r.released_at}
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}
