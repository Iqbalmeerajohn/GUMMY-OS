"use client";

import { useState } from "react";
import { Calendar, Check, Target, X } from "lucide-react";

import { getPriorityMeta } from "@/config/goals";
import type { GoalCandidate } from "@/lib/api/resources";
import {
  candidateToCreateBody,
  candidateToDismissBody,
  formatTargetDate,
} from "@/lib/goals/goalCandidate";
import { useGoalFromConversation } from "@/lib/goals/useGoals";
import { cn } from "@/lib/utils";

/**
 * "Goal Detected" inline prompt (M5.5). Rendered beneath an assistant reply
 * when GUMMY spots a goal-like statement in the user's message. Mirrors the
 * memory-confirmation philosophy: consent before persistence — the goal is only
 * created when the user clicks **Create Goal**. No modal.
 */
export function GoalConfirmation({
  candidate,
  conversationId,
  onResolved,
}: {
  candidate: GoalCandidate;
  conversationId: string | null;
  onResolved: (decision: "created" | "dismissed") => void;
}) {
  const { accept, dismiss, isAccepting, isDismissing } =
    useGoalFromConversation();
  const [busy, setBusy] = useState(false);

  const priority = getPriorityMeta(candidate.priority);
  const target = formatTargetDate(candidate.target_date);
  const pending = busy || isAccepting || isDismissing;

  async function onCreate() {
    if (pending) return;
    setBusy(true);
    try {
      await accept(candidateToCreateBody(candidate, conversationId));
      onResolved("created");
    } catch {
      // The hook surfaces a toast; keep the card so the user can retry.
      setBusy(false);
    }
  }

  async function onDismiss() {
    if (pending) return;
    setBusy(true);
    try {
      await dismiss(candidateToDismissBody(candidate, conversationId));
    } catch {
      // Dismissal is best-effort; hide the card regardless.
    }
    onResolved("dismissed");
  }

  return (
    <div className="glass border-primary/20 mt-2 rounded-xl border p-3.5">
      <div className="flex items-center gap-2">
        <span className="bg-primary/10 text-primary grid size-7 place-items-center rounded-lg">
          <Target className="size-4" />
        </span>
        <div className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
          Goal Detected
        </div>
      </div>

      <p className="mt-2 text-sm font-medium">{candidate.title}</p>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium",
            priority.chip,
          )}
        >
          <span className={cn("size-1.5 rounded-full", priority.dot)} />
          {priority.label} priority
        </span>
        {target ? (
          <span className="text-muted-foreground inline-flex items-center gap-1 text-xs">
            <Calendar className="size-3" />
            {target}
          </span>
        ) : null}
      </div>

      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          onClick={onCreate}
          disabled={pending}
          className="bg-primary text-primary-foreground hover:bg-primary/90 inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-xs font-medium transition-colors disabled:opacity-60"
        >
          <Check className="size-3.5" />
          {isAccepting ? "Creating…" : "Create Goal"}
        </button>
        <button
          type="button"
          onClick={onDismiss}
          disabled={pending}
          className="text-muted-foreground hover:bg-accent hover:text-foreground inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-xs font-medium transition-colors disabled:opacity-60"
        >
          <X className="size-3.5" />
          Dismiss
        </button>
      </div>
    </div>
  );
}
