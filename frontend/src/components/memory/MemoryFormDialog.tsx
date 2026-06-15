"use client";

import { useState } from "react";

import {
  MEMORY_CATEGORIES,
  MEMORY_IMPORTANCE,
  type MemoryCategory,
  type MemoryImportance,
} from "@/config/memory";
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
import { getIcon } from "@/lib/icons";
import { cn } from "@/lib/utils";
import type { MemoryDraft } from "@/lib/memory/store";
import type { Memory } from "@/lib/memory/types";

/** Add or edit a memory. Controlled; submits a draft to the caller. */
export function MemoryFormDialog({
  open,
  onOpenChange,
  mode,
  initial,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: "add" | "edit";
  initial?: Memory | null;
  onSubmit: (draft: MemoryDraft) => void;
}) {
  const [content, setContent] = useState("");
  const [category, setCategory] = useState<MemoryCategory>("personal");
  const [importance, setImportance] = useState<MemoryImportance>("medium");

  // Seed the form from `initial` on each open transition — the React-recommended
  // "adjust state during render" pattern (no effect, no cascading renders).
  const [wasOpen, setWasOpen] = useState(false);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setContent(initial?.content ?? "");
      setCategory(initial?.category ?? "personal");
      setImportance(initial?.importance ?? "medium");
    }
  }

  const canSave = content.trim().length > 0;

  function handleSave() {
    if (!canSave) return;
    onSubmit({ content: content.trim(), category, importance });
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {mode === "add" ? "Teach GUMMY something" : "Edit memory"}
          </DialogTitle>
          <DialogDescription>
            {mode === "add"
              ? "Add a fact for GUMMY to remember about you."
              : "Update what GUMMY remembers. Previous versions are kept."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label
              htmlFor="memory-content"
              className="text-muted-foreground text-xs font-medium"
            >
              Memory
            </label>
            <textarea
              id="memory-content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={3}
              autoFocus
              placeholder="e.g. Prefers concise answers without filler."
              className="border-input focus-visible:border-ring focus-visible:ring-ring/50 dark:bg-input/30 w-full resize-none rounded-lg border bg-transparent px-2.5 py-2 text-sm outline-none focus-visible:ring-3"
            />
          </div>

          <Fieldset label="Category">
            {MEMORY_CATEGORIES.map((c) => {
              const Icon = getIcon(c.icon);
              const active = category === c.id;
              return (
                <Chip
                  key={c.id}
                  active={active}
                  onClick={() => setCategory(c.id)}
                >
                  <Icon className="size-3" />
                  {c.label}
                </Chip>
              );
            })}
          </Fieldset>

          <Fieldset label="Importance">
            {MEMORY_IMPORTANCE.map((i) => (
              <Chip
                key={i.id}
                active={importance === i.id}
                onClick={() => setImportance(i.id)}
              >
                {i.label}
              </Chip>
            ))}
          </Fieldset>
        </div>

        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>Cancel</DialogClose>
          <Button onClick={handleSave} disabled={!canSave}>
            {mode === "add" ? "Save memory" : "Save changes"}
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
      <span className="text-muted-foreground text-xs font-medium">{label}</span>
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
