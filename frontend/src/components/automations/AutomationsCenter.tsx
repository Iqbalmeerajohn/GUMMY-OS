"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Pause, Play, Trash2, Zap } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  deleteAutomation,
  listAutomations,
  toggleAutomation,
  type AutomationItem,
} from "@/lib/api/resources";
import { cn } from "@/lib/utils";

/**
 * Automations — the scheduled work GUMMY runs locally.
 *
 * Read-and-manage only: automations are created through conversation, so there
 * is no "New automation" form here. That keeps one path into the table and
 * means every automation carries the agent trace that created it.
 *
 * The panel exists mostly to make a promise checkable. When GUMMY says it
 * scheduled a reminder, this is where the user confirms it actually did.
 */

const SCHEDULE_LABEL: Record<string, string> = {
  once: "Once",
  daily: "Every day",
  weekly: "Every week",
};

const KIND_LABEL: Record<string, string> = {
  reminder: "Reminder",
  goal_check_in: "Goal check-in",
  digest: "Summary",
};

function formatWhen(iso: string | null): string {
  if (!iso) return "—";
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "—";
  return when.toLocaleString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StatusPill({ item }: { item: AutomationItem }) {
  // Status is shown as form as well as text, so what needs attention reads at
  // a glance rather than requiring the label to be parsed.
  const tone =
    item.status === "failed"
      ? "border-destructive/40 bg-destructive/10 text-destructive"
      : item.status === "completed"
        ? "border-border bg-muted text-muted-foreground"
        : item.enabled
          ? "border-primary/30 bg-primary/10 text-primary"
          : "border-amber-400/30 bg-amber-400/10 text-amber-300";
  const label =
    item.status === "failed"
      ? "Failed"
      : item.status === "completed"
        ? "Done"
        : item.enabled
          ? "Active"
          : "Paused";
  return (
    <span
      className={cn(
        "rounded-full border px-2 py-0.5 text-[11px] font-medium",
        tone,
      )}
    >
      {label}
    </span>
  );
}

export function AutomationsCenter() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["automations"],
    queryFn: listAutomations,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["automations"] });

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      toggleAutomation(id, enabled),
    onSuccess: (item) => {
      invalidate();
      toast.success(item.enabled ? "Automation resumed" : "Automation paused");
    },
    onError: () => toast.error("Could not update that automation"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteAutomation(id),
    onSuccess: () => {
      invalidate();
      toast.success("Automation deleted");
    },
    onError: () => toast.error("Could not delete that automation"),
  });

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }

  const items = data?.items ?? [];

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
        <Zap className="text-muted-foreground size-8" />
        <p className="text-sm font-medium">No automations yet</p>
        <p className="text-muted-foreground max-w-xs text-xs">
          Ask GUMMY in chat — &ldquo;remind me tomorrow at 9am to review my
          goals&rdquo; — and it will appear here.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 p-4">
      {items.map((item) => (
        <div
          key={item.id}
          className="border-border bg-card/50 flex flex-col gap-2 rounded-xl border p-3"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{item.name}</p>
              {item.description && item.description !== item.name ? (
                <p className="text-muted-foreground truncate text-xs">
                  {item.description}
                </p>
              ) : null}
            </div>
            <StatusPill item={item} />
          </div>

          <div className="text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <span className="flex items-center gap-1">
              <Clock className="size-3" />
              {SCHEDULE_LABEL[item.schedule] ?? item.schedule}
            </span>
            <span>{KIND_LABEL[item.kind] ?? item.kind}</span>
            <span>Next: {formatWhen(item.next_run_at)}</span>
            {item.last_run_at ? (
              <span>Last: {formatWhen(item.last_run_at)}</span>
            ) : null}
          </div>

          {item.last_error ? (
            <p className="text-destructive text-xs">{item.last_error}</p>
          ) : null}

          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              disabled={item.status === "completed" || toggle.isPending}
              onClick={() =>
                toggle.mutate({ id: item.id, enabled: !item.enabled })
              }
            >
              {item.enabled ? (
                <>
                  <Pause className="mr-1 size-3" /> Pause
                </>
              ) : (
                <>
                  <Play className="mr-1 size-3" /> Resume
                </>
              )}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-muted-foreground hover:text-destructive h-7 px-2 text-xs"
              disabled={remove.isPending}
              onClick={() => remove.mutate(item.id)}
            >
              <Trash2 className="mr-1 size-3" /> Delete
            </Button>
          </div>
        </div>
      ))}
      <p className="text-muted-foreground px-1 pt-1 text-[11px]">
        Automations run inside GUMMY while it is open. They do not send email or
        create calendar events.
      </p>
    </div>
  );
}
