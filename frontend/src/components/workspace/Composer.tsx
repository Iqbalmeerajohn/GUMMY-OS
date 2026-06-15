"use client";

import { Mic, Paperclip, SendHorizonal, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { buttonVariants } from "@/components/ui/button";
import { MODALITY_CAPABILITIES } from "@/lib/chat/types";
import { cn } from "@/lib/utils";

/**
 * Workspace composer. Text is live; attachment / voice / workflow controls are
 * architecture seams (see lib/chat/types) — present and wired to the multimodal
 * capability registry, but not yet functional.
 */
export function Composer({
  value,
  onChange,
  onSend,
  disabled = false,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled?: boolean;
}) {
  const canSend = value.trim().length > 0 && !disabled;

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (canSend) onSend();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) onSend();
    }
  }

  const planned = (label: string) =>
    toast.info(`${label} is planned — coming to GUMMY soon.`);

  const attachNote = MODALITY_CAPABILITIES.filter((m) => m.modality !== "text")
    .map((m) => m.modality)
    .join(", ");

  return (
    <form onSubmit={submit} className="glass elevation-2 rounded-2xl p-2">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        rows={1}
        placeholder="Message GUMMY…"
        className="max-h-40 min-h-10 w-full resize-none bg-transparent px-2 py-1.5 text-sm outline-none"
      />
      <div className="flex items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-0.5">
          <IconButton
            label="Attach"
            onClick={() => planned(`Attachments (${attachNote})`)}
          >
            <Paperclip className="size-4" />
          </IconButton>
          <IconButton label="Voice" onClick={() => planned("Voice input")}>
            <Mic className="size-4" />
          </IconButton>
          <IconButton
            label="Workflows"
            onClick={() => planned("Workflow learning")}
          >
            <Sparkles className="size-4" />
          </IconButton>
        </div>
        <button
          type="submit"
          disabled={!canSend}
          aria-label="Send"
          className={cn(buttonVariants({ size: "icon" }), "size-9 rounded-xl")}
        >
          <SendHorizonal className="size-4" />
        </button>
      </div>
    </form>
  );
}

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="text-muted-foreground hover:bg-accent hover:text-foreground grid size-9 place-items-center rounded-xl transition-colors"
    >
      {children}
    </button>
  );
}
