"use client";

import Link from "next/link";
import { toast } from "sonner";
import {
  Brain,
  Compass,
  ListChecks,
  MessageSquare,
  Target,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";

import { useAuth } from "@/components/auth/AuthProvider";
import { LivingOrb } from "@/components/brand/LivingOrb";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  useActiveGoals,
  useRecentConversations,
  useRecentMemories,
} from "@/lib/hooks/useDashboard";
import {
  QUICK_START_SUGGESTIONS,
  RECOMMENDED_ACTIONS,
} from "@/config/dashboard";
import { formatRelativeTime, timeOfDayGreeting } from "@/lib/format";

const ICONS: Record<string, LucideIcon> = {
  Compass,
  Brain,
  Target,
  ListChecks,
  MessageSquare,
};

const SOON = "Arrives with the feature milestones (M3+).";

export function GreetingHeader() {
  const { user } = useAuth();
  const name = user?.email?.split("@")[0];
  return (
    <div className="flex items-center gap-5">
      <LivingOrb size={72} state="idle" className="shrink-0" />
      <div>
        <h1 className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
          {timeOfDayGreeting()}
          {name ? <span className="text-primary">, {name}</span> : null}
        </h1>
        <p className="text-muted-foreground mt-1 text-sm sm:text-base">
          Here&apos;s your operating system at a glance.
        </p>
      </div>
    </div>
  );
}

function SectionCard({
  title,
  children,
  className,
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={"glass elevation-2 rounded-2xl p-5 " + (className ?? "")}
    >
      <h2 className="text-muted-foreground mb-4 text-xs font-medium tracking-[0.15em] uppercase">
        {title}
      </h2>
      {children}
    </section>
  );
}

function EmptyState({ icon: Icon, text }: { icon: LucideIcon; text: string }) {
  return (
    <div className="text-muted-foreground flex flex-col items-center gap-2 py-6 text-center text-sm">
      <Icon className="size-5 opacity-60" />
      <span className="text-balance">{text}</span>
    </div>
  );
}

function LoadingRows() {
  return (
    <div className="space-y-2.5">
      <Skeleton className="h-9 w-full rounded-lg" />
      <Skeleton className="h-9 w-4/5 rounded-lg" />
      <Skeleton className="h-9 w-3/5 rounded-lg" />
    </div>
  );
}

export function RecentMemoriesWidget() {
  const { data, isLoading, isError } = useRecentMemories();
  const items = data?.items ?? [];
  return (
    <SectionCard title="Recent Memories">
      {isLoading ? (
        <LoadingRows />
      ) : isError || items.length === 0 ? (
        <EmptyState
          icon={Brain}
          text="No memories yet. GUMMY will remember what matters as you chat."
        />
      ) : (
        <ul className="space-y-2.5">
          {items.map((m) => (
            <li
              key={m.id}
              className="border-border/50 bg-background/40 flex items-start gap-2 rounded-lg border p-2.5"
            >
              <Badge variant="secondary" className="shrink-0 text-[10px]">
                {m.category}
              </Badge>
              <span className="line-clamp-2 text-sm">{m.content}</span>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

export function GoalsWidget() {
  const { data, isLoading, isError } = useActiveGoals();
  const items = data?.items ?? [];
  return (
    <SectionCard title="Goals">
      {isLoading ? (
        <LoadingRows />
      ) : isError || items.length === 0 ? (
        <EmptyState
          icon={Target}
          text="No active goals. Set one to start tracking progress."
        />
      ) : (
        <ul className="space-y-2.5">
          {items.map((g) => (
            <li
              key={g.id}
              className="border-border/50 bg-background/40 flex items-center justify-between gap-2 rounded-lg border p-2.5"
            >
              <span className="line-clamp-1 text-sm font-medium">
                {g.title}
              </span>
              <Badge variant="secondary" className="shrink-0 text-[10px]">
                {g.status}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

export function ActivityWidget() {
  const { data, isLoading, isError } = useRecentConversations();
  const items = data?.items ?? [];
  return (
    <SectionCard title="Activity">
      {isLoading ? (
        <LoadingRows />
      ) : isError || items.length === 0 ? (
        <EmptyState
          icon={MessageSquare}
          text="No activity yet. Your recent work will appear here."
        />
      ) : (
        <ul className="space-y-2.5">
          {items.map((c) => (
            <li
              key={c.id}
              className="border-border/50 bg-background/40 flex items-center justify-between gap-2 rounded-lg border p-2.5"
            >
              <span className="line-clamp-1 text-sm">
                {c.title ?? "Untitled conversation"}
              </span>
              <span className="text-muted-foreground shrink-0 text-xs">
                {formatRelativeTime(c.last_message_at)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

export function RecommendedActionsWidget() {
  return (
    <SectionCard title="Recommended Actions">
      <div className="grid gap-2.5 sm:grid-cols-3">
        {RECOMMENDED_ACTIONS.map((a) => {
          const Icon = ICONS[a.icon] ?? Compass;
          const inner = (
            <div className="border-border/50 bg-background/40 hover:border-primary/40 flex h-full flex-col gap-2 rounded-xl border p-4 text-left transition-colors">
              <Icon className="text-primary size-5" />
              <span className="text-sm font-medium">{a.title}</span>
              <span className="text-muted-foreground text-xs">
                {a.description}
              </span>
            </div>
          );
          return a.href ? (
            <Link key={a.id} href={a.href}>
              {inner}
            </Link>
          ) : (
            <button
              key={a.id}
              type="button"
              onClick={() => toast.info(SOON)}
              className="text-left"
            >
              {inner}
            </button>
          );
        })}
      </div>
    </SectionCard>
  );
}

export function QuickStartWidget() {
  return (
    <SectionCard title="Quick Start">
      <div className="flex flex-wrap gap-2">
        {QUICK_START_SUGGESTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => toast.info(SOON)}
            className="glass hover:border-primary/40 rounded-full px-3.5 py-1.5 text-sm transition-colors"
          >
            {s}
          </button>
        ))}
      </div>
    </SectionCard>
  );
}
