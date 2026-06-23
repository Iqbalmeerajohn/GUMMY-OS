"use client";

import { useState } from "react";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { GOAL_CATEGORY_SUGGESTIONS, GOAL_PRIORITIES } from "@/config/goals";
import type {
  GoalCreateBody,
  GoalItem,
  GoalPriority,
} from "@/lib/api/resources";
import { cn } from "@/lib/utils";

/** ISO date (YYYY-MM-DD) for the native date input, or "" when unset. */
function toDateInput(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toISOString().slice(0, 10);
}

/**
 * Create or edit a goal. Controlled; submits a goal body to the caller. On
 * edit, only the editable attributes are surfaced (status changes go through
 * the dedicated complete/archive actions).
 */
export function GoalForm({
  open,
  onOpenChange,
  mode,
  initial,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: "add" | "edit";
  initial?: GoalItem | null;
  onSubmit: (body: GoalCreateBody) => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState<GoalPriority>("medium");
  const [targetDate, setTargetDate] = useState("");

  // Seed from `initial` on each open transition (adjust-state-during-render).
  const [wasOpen, setWasOpen] = useState(false);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setTitle(initial?.title ?? "");
      setDescription(initial?.description ?? "");
      setCategory(initial?.category ?? "");
      setPriority(initial?.priority ?? "medium");
      setTargetDate(toDateInput(initial?.target_date));
    }
  }

  const canSave = title.trim().length > 0;

  function handleSave() {
    if (!canSave) return;
    onSubmit({
      title: title.trim(),
      description: description.trim() || null,
      category: category.trim() || null,
      priority,
      target_date: targetDate ? targetDate : null,
    });
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {mode === "add" ? "New goal" : "Edit goal"}
          </DialogTitle>
          <DialogDescription>
            {mode === "add"
              ? "Tell GUMMY what you're working toward."
              : "Update this goal's details."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label
              htmlFor="goal-title"
              className="text-muted-foreground text-xs font-medium"
            >
              Title
            </label>
            <input
              id="goal-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
              placeholder="e.g. Land a senior systems role"
              className="border-input focus-visible:border-ring focus-visible:ring-ring/50 dark:bg-input/30 w-full rounded-lg border bg-transparent px-2.5 py-2 text-sm outline-none focus-visible:ring-3"
            />
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="goal-description"
              className="text-muted-foreground text-xs font-medium"
            >
              Description
            </label>
            <textarea
              id="goal-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="Optional context to keep GUMMY aligned."
              className="border-input focus-visible:border-ring focus-visible:ring-ring/50 dark:bg-input/30 w-full resize-none rounded-lg border bg-transparent px-2.5 py-2 text-sm outline-none focus-visible:ring-3"
            />
          </div>

          <Fieldset label="Priority">
            {GOAL_PRIORITIES.map((p) => (
              <Chip
                key={p.id}
                active={priority === p.id}
                onClick={() => setPriority(p.id)}
              >
                {p.label}
              </Chip>
            ))}
          </Fieldset>

          <div className="space-y-1.5">
            <label
              htmlFor="goal-category"
              className="text-muted-foreground text-xs font-medium"
            >
              Category
            </label>
            <input
              id="goal-category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="e.g. Career"
              className="border-input focus-visible:border-ring focus-visible:ring-ring/50 dark:bg-input/30 w-full rounded-lg border bg-transparent px-2.5 py-2 text-sm outline-none focus-visible:ring-3"
            />
            <div className="flex flex-wrap gap-1.5 pt-1">
              {GOAL_CATEGORY_SUGGESTIONS.map((c) => (
                <Chip
                  key={c}
                  active={category === c}
                  onClick={() => setCategory(c)}
                >
                  {c}
                </Chip>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="goal-target"
              className="text-muted-foreground text-xs font-medium"
            >
              Target date
            </label>
            <input
              id="goal-target"
              type="date"
              value={targetDate}
              onChange={(e) => setTargetDate(e.target.value)}
              className="border-input focus-visible:border-ring focus-visible:ring-ring/50 dark:bg-input/30 w-full rounded-lg border bg-transparent px-2.5 py-2 text-sm outline-none focus-visible:ring-3"
            />
          </div>
        </div>

        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>
            Cancel
          </DialogClose>
          <Button onClick={handleSave} disabled={!canSave}>
            {mode === "add" ? "Create goal" : "Save changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Fieldset({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <span className="text-muted-foreground text-xs font-medium">
        {label}
      </span>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
        active
          ? "border-primary/40 bg-primary/15 text-primary"
          : "border-border text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}
