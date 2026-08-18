"use client";

import {
  CheckCircle2,
  CircleDashed,
  Loader2,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * What GUMMY is doing, while it does it.
 *
 * A tool-using turn takes several seconds and, without this, shows nothing at
 * all — the reply cannot stream token-by-token because the model may call a
 * tool, read the result, and only then answer. So the progress *is* the
 * streaming here, and it has to carry real information rather than a spinner.
 *
 * Everything shown comes from the backend's `status` / `tool_status` events,
 * which carry a stage name and a tool label and nothing else. No prompts, no
 * tool arguments, no chain-of-thought: the user learns what happened, not what
 * the model was thinking.
 */

export interface ActivityStep {
  id: string;
  /** Display label, e.g. "Searching your files". */
  label: string;
  state: "running" | "done" | "failed" | "approval";
}

/** Orchestrator stages, in the user's language rather than the system's. */
const STAGE_LABELS: Record<string, string> = {
  understanding: "Understanding your request",
  retrieving_context: "Retrieving relevant memory",
  gathering: "Gathering context",
  delegating: "Delegating to a specialist",
  answering: "Preparing the answer",
};

export function stageLabel(stage: string): string | null {
  return STAGE_LABELS[stage] ?? null;
}

function Icon({ state }: { state: ActivityStep["state"] }) {
  if (state === "running")
    return <Loader2 className="text-primary size-3.5 shrink-0 animate-spin" />;
  if (state === "done")
    return <CheckCircle2 className="text-primary size-3.5 shrink-0" />;
  if (state === "approval")
    return <ShieldAlert className="size-3.5 shrink-0 text-amber-400" />;
  return <XCircle className="text-destructive size-3.5 shrink-0" />;
}

export function ActivityTrail({
  steps,
  className,
}: {
  steps: ActivityStep[];
  className?: string;
}) {
  if (steps.length === 0) return null;

  return (
    <ul
      className={cn("flex flex-col gap-1.5 text-xs", className)}
      // Progress is supplementary to the reply: announced politely so it does
      // not interrupt a screen reader mid-sentence.
      aria-live="polite"
    >
      {steps.map((step) => (
        <li
          key={step.id}
          className={cn(
            "flex items-center gap-2",
            step.state === "done" && "text-muted-foreground",
            step.state === "running" && "text-foreground",
            step.state === "failed" && "text-muted-foreground",
            step.state === "approval" && "text-amber-300",
          )}
        >
          <Icon state={step.state} />
          <span className={cn(step.state === "failed" && "line-through")}>
            {step.label}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** A resting placeholder while the first event is in flight. */
export function ActivityPending({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "text-muted-foreground flex items-center gap-2 text-xs",
        className,
      )}
    >
      <CircleDashed className="size-3.5 animate-pulse" />
      <span>Thinking</span>
    </div>
  );
}
