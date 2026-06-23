"use client";

import { useRef } from "react";
import {
  FileText,
  Loader2,
  Mic,
  Paperclip,
  SendHorizonal,
  Sparkles,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Mirrors the backend SUPPORTED_FILE_MIME_TYPES (M6 MVP + cheap extras).
const ATTACH_ACCEPT = ".pdf,.txt,.md,.markdown,.docx,.csv,.xlsx";

export interface ComposerAttachment {
  id: string;
  name: string;
}

/**
 * Workspace composer. Text + file attachments are live (M6.5 File
 * Intelligence): an attached file is uploaded immediately and its content
 * grounds the next reply. Voice / workflow controls remain architecture seams.
 */
export function Composer({
  value,
  onChange,
  onSend,
  disabled = false,
  attachments = [],
  onAttach,
  onRemoveAttachment,
  uploadingAttachment = false,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled?: boolean;
  attachments?: ComposerAttachment[];
  onAttach?: (file: File) => void;
  onRemoveAttachment?: (id: string) => void;
  uploadingAttachment?: boolean;
}) {
  const canSend = value.trim().length > 0 && !disabled;
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  function onPickFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files;
    if (files && onAttach) {
      for (const file of Array.from(files)) onAttach(file);
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  const planned = (label: string) =>
    toast.info(`${label} is planned — coming to GUMMY soon.`);

  return (
    <form onSubmit={submit} className="glass elevation-2 rounded-2xl p-2">
      {attachments.length > 0 ? (
        <div className="flex flex-wrap gap-1.5 px-1 pb-2">
          {attachments.map((a) => (
            <span
              key={a.id}
              className="border-border/60 bg-background/60 inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-xs"
            >
              <FileText className="text-primary size-3.5 shrink-0" />
              <span className="max-w-40 truncate">{a.name}</span>
              <button
                type="button"
                aria-label={`Remove ${a.name}`}
                onClick={() => onRemoveAttachment?.(a.id)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      ) : null}
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        rows={1}
        placeholder="Message GUMMY…"
        // text-base (16px) on mobile prevents iOS Safari from zooming on focus.
        className="max-h-40 min-h-10 w-full resize-none bg-transparent px-2 py-1.5 text-base outline-none sm:text-sm"
      />
      <div className="flex items-center justify-between gap-2 px-1">
        <div className="flex items-center gap-0.5">
          <input
            ref={fileInputRef}
            type="file"
            accept={ATTACH_ACCEPT}
            multiple
            className="hidden"
            onChange={onPickFiles}
          />
          <IconButton
            label="Attach a file"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadingAttachment || disabled}
          >
            {uploadingAttachment ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Paperclip className="size-4" />
            )}
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
          className={cn(
            buttonVariants({ size: "icon" }),
            "size-11 rounded-xl sm:size-9",
          )}
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
  disabled = false,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className="text-muted-foreground hover:bg-accent hover:text-foreground grid size-11 place-items-center rounded-xl transition-colors disabled:cursor-not-allowed disabled:opacity-50 sm:size-9"
    >
      {children}
    </button>
  );
}
