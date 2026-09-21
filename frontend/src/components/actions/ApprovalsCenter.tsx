"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Check, ShieldAlert, ShieldCheck, Terminal, X } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  approveAction,
  listApprovals,
  rejectAction,
  type ActionApproval,
  type ApprovalTier,
} from "@/lib/api/resources";
import { cn } from "@/lib/utils";

/**
 * The confirm-before-acting queue — where consequential actions wait for you.
 *
 * Every tool GUMMY can run carries a tier. Green is read-only and runs
 * immediately. Yellow can change something and Red is irreversible, so both
 * stop here and do nothing until a human decides. Until this panel existed,
 * those actions could be proposed and gated but never approved, which meant
 * the entire Yellow/Red half of the catalog was unreachable.
 *
 * Two things this screen takes seriously.
 *
 * **It shows the actual call, not a summary.** The exact arguments are on
 * screen, because those same stored bytes are what the backend executes — it
 * never re-reads them from the approve request. What you read is what runs.
 *
 * **Approving and succeeding are different events.** The approval always
 * records; the action it authorises can still fail against the machine. The
 * result is reported separately rather than folded into the approval, so a
 * failed command never looks like a failed decision.
 */

const TIER_STYLE: Record<ApprovalTier, string> = {
  green: "border-emerald-500/30 bg-emerald-500/5 text-emerald-300",
  yellow: "border-amber-500/40 bg-amber-500/5 text-amber-300",
  red: "border-red-500/40 bg-red-500/5 text-red-300",
};

const TIER_LABEL: Record<ApprovalTier, string> = {
  green: "Read-only",
  yellow: "Changes something",
  red: "Irreversible",
};

/** A short, plain-English line for what this action will do. */
function describe(approval: ActionApproval): string {
  const args = (approval.preview?.args ?? {}) as Record<string, unknown>;
  switch (approval.action_kind) {
    case "shell_exec":
      return `Run \`${String(args.command ?? "")}\` in ${String(args.cwd ?? "?")}`;
    case "workspace_write":
      return `Overwrite ${String(args.path ?? "?")}`;
    case "email_send":
      return `Email ${String(args.to ?? "?")} — "${String(args.subject ?? "")}"`;
    default:
      return approval.action_kind.replace(/_/g, " ");
  }
}

function expiresIn(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "expired";
  const minutes = Math.round(ms / 60000);
  if (minutes < 60) return `expires in ${minutes}m`;
  return `expires in ${Math.round(minutes / 60)}h`;
}

export function ApprovalsCenter() {
  const queryClient = useQueryClient();
  const [lastResult, setLastResult] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["approvals", "pending"],
    queryFn: () => listApprovals("pending"),
    // A queue is only useful if it is current; an action approved elsewhere
    // (or expiring) should disappear without a manual refresh.
    refetchInterval: 10_000,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["approvals"] });
  };

  const approve = useMutation({
    mutationFn: approveAction,
    onSuccess: (decision) => {
      invalidate();
      const run = decision.execution;
      if (!run || !run.executed) {
        toast.success("Approved", {
          description: run?.error ?? "Nothing was left to run.",
        });
        return;
      }
      if (run.outcome === "success") {
        toast.success(`${run.tool_key} ran`, {
          description: `Finished in ${Math.round(run.duration_ms)}ms.`,
        });
        setLastResult(JSON.stringify(run.output, null, 2));
      } else {
        // Approved, then failed. Said plainly rather than as a success.
        toast.error(`${run.tool_key} failed`, { description: run.error ?? "" });
        setLastResult(run.error);
      }
    },
    onError: (error: Error) =>
      toast.error("Could not approve", { description: error.message }),
  });

  const reject = useMutation({
    mutationFn: rejectAction,
    onSuccess: () => {
      invalidate();
      toast.success("Rejected", { description: "Nothing was run." });
    },
    onError: (error: Error) =>
      toast.error("Could not reject", { description: error.message }),
  });

  const busy = approve.isPending || reject.isPending;
  const items = data?.items ?? [];

  if (isLoading) {
    return (
      <div className="space-y-3 p-1">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
        <ShieldCheck className="text-muted-foreground/40 h-10 w-10" />
        <p className="text-sm font-medium">Nothing waiting</p>
        <p className="text-muted-foreground max-w-xs text-xs leading-relaxed">
          Actions that change something on your machine pause here first.
          Read-only work runs without asking.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3 p-1">
      {items.map((approval) => {
        const args = (approval.preview?.args ?? {}) as Record<string, unknown>;
        return (
          <article
            key={approval.id}
            className={cn(
              "rounded-lg border p-4 transition-colors",
              TIER_STYLE[approval.tier],
            )}
          >
            <header className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {approval.tier === "red" ? (
                    <ShieldAlert className="h-4 w-4 shrink-0" />
                  ) : (
                    <Terminal className="h-4 w-4 shrink-0" />
                  )}
                  <span className="truncate text-sm font-semibold">
                    {describe(approval)}
                  </span>
                </div>
                <p className="text-muted-foreground mt-1 text-xs">
                  {TIER_LABEL[approval.tier]} · asked by {approval.agent_key} ·{" "}
                  {expiresIn(approval.expires_at)}
                </p>
              </div>
            </header>

            {/* The exact arguments, because these are the bytes that run. */}
            <pre className="bg-background/60 mt-3 max-h-40 overflow-auto rounded border border-white/5 p-2 font-mono text-[11px] leading-relaxed">
              {JSON.stringify(args, null, 2)}
            </pre>

            <footer className="mt-3 flex items-center gap-2">
              <Button
                size="sm"
                disabled={busy}
                onClick={() => approve.mutate(approval.id)}
              >
                <Check className="mr-1 h-3.5 w-3.5" />
                Approve and run
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={busy}
                onClick={() => reject.mutate(approval.id)}
              >
                <X className="mr-1 h-3.5 w-3.5" />
                Reject
              </Button>
            </footer>
          </article>
        );
      })}

      {lastResult ? (
        <section className="mt-4">
          <h3 className="text-muted-foreground mb-1 text-xs font-medium">
            Last result
          </h3>
          <pre className="bg-background/60 max-h-48 overflow-auto rounded border border-white/5 p-2 font-mono text-[11px] leading-relaxed">
            {lastResult}
          </pre>
        </section>
      ) : null}
    </div>
  );
}
