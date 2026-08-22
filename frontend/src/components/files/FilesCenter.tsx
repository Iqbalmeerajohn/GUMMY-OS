"use client";

import { useRef, useState } from "react";
import { FileText, Loader2, RefreshCw, Trash2, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useFileActions,
  useFilesQuery,
  useFileStats,
} from "@/lib/files/useFiles";
import type { FileItem } from "@/lib/api/resources";
import { canReindex, fileState, type FileState } from "@/lib/files/fileState";
import { formatBytes, formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

// Mirrors the backend's SUPPORTED_FILE_MIME_TYPES (M6 MVP + cheap extras).
const ACCEPT = ".pdf,.txt,.md,.markdown,.docx,.csv,.xlsx";

const STATUS_META: Record<
  FileState,
  { label: string; className: string; hint: string }
> = {
  searchable: {
    label: "Searchable",
    className: "border-primary/40 bg-primary/15 text-primary",
    hint: "GUMMY can answer questions from this file.",
  },
  unindexed: {
    label: "Not indexed",
    className: "border-amber-500/40 bg-amber-500/15 text-amber-500",
    hint: "Text was extracted but never embedded, so this file cannot be searched yet. Re-index it.",
  },
  processing: {
    label: "Indexing",
    className: "border-amber-500/40 bg-amber-500/15 text-amber-500",
    hint: "Extracting and embedding — searchable when it finishes.",
  },
  pending: {
    label: "Pending",
    className: "border-border text-muted-foreground",
    hint: "Queued for indexing.",
  },
  failed: {
    label: "Failed",
    className: "border-red-500/40 bg-red-500/15 text-red-500",
    hint: "This file could not be indexed. Re-index to try again.",
  },
};

/**
 * Files — upload documents into GUMMY's knowledge system, then view and manage
 * them. Production-ready MVP (M6): upload, list (with processing status), and
 * delete. TanStack Query is the single source of truth.
 */
export function FilesCenter() {
  const { data: files, isLoading } = useFilesQuery();
  const { data: stats } = useFileStats();
  const actions = useFileActions();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  async function handleFiles(list: FileList | null) {
    if (!list || list.length === 0) return;
    for (const file of Array.from(list)) {
      await actions.upload(file);
    }
    if (inputRef.current) inputRef.current.value = "";
  }

  const items = files ?? [];
  const totalChunks = items.reduce((sum, f) => sum + f.chunk_count, 0);
  const searchable = items.filter((f) => fileState(f) === "searchable");
  // Files the user can fix, as opposed to files that are merely still working.
  const needsAttention = items.filter((f) => {
    const state = fileState(f);
    return state === "unindexed" || state === "failed";
  });

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
            Files
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Upload documents into GUMMY&apos;s knowledge system — they become
            part of your long-term memory.
          </p>
        </div>
        <Button
          onClick={() => inputRef.current?.click()}
          disabled={actions.isUploading}
        >
          {actions.isUploading ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Upload className="size-4" />
          )}
          Upload file
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </header>

      <div className="grid grid-cols-3 gap-2.5 sm:max-w-md">
        <Stat label="Files" value={stats?.total ?? items.length} />
        <Stat label="Indexed chunks" value={totalChunks} />
        <Stat label="Searchable" value={searchable.length} />
      </div>

      {needsAttention.length > 0 ? (
        <div className="glass elevation-2 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/40 p-3.5">
          <p className="text-muted-foreground text-sm">
            <span className="text-foreground font-medium">
              {needsAttention.length}{" "}
              {needsAttention.length === 1 ? "file is" : "files are"} not
              searchable.
            </span>{" "}
            GUMMY cannot answer questions from{" "}
            {needsAttention.length === 1 ? "it" : "them"} until{" "}
            {needsAttention.length === 1 ? "it is" : "they are"} indexed.
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => needsAttention.forEach((f) => actions.reindex(f.id))}
            disabled={actions.reindexingId !== null}
          >
            <RefreshCw className="size-4" />
            Index {needsAttention.length === 1 ? "it" : "all"}
          </Button>
        </div>
      ) : null}

      {/* Drop zone */}
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void handleFiles(e.dataTransfer.files);
        }}
        className={cn(
          "glass flex w-full flex-col items-center gap-2 rounded-2xl border border-dashed px-6 py-10 text-center transition-colors",
          dragging
            ? "border-primary/60 bg-primary/10"
            : "border-border hover:border-primary/40",
        )}
      >
        <Upload className="text-primary size-6" />
        <span className="text-sm font-medium">
          Drag &amp; drop, or click to upload
        </span>
        <span className="text-muted-foreground text-xs">
          PDF, TXT, MD, DOCX, CSV, XLSX
        </span>
      </button>

      {isLoading ? (
        <div className="space-y-2.5">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="space-y-2.5">
          {items.map((file) => (
            <FileRow
              key={file.id}
              file={file}
              onDelete={() => actions.remove(file.id)}
              onReindex={() => actions.reindex(file.id)}
              reindexing={actions.reindexingId === file.id}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function FileRow({
  file,
  onDelete,
  onReindex,
  reindexing,
}: {
  file: FileItem;
  onDelete: () => void;
  onReindex: () => void;
  reindexing: boolean;
}) {
  const state = fileState(file);
  const status = STATUS_META[state];
  // Offered only where it does something: a searchable file needs no repair,
  // and one still indexing would just be interrupted.
  const repairable = canReindex(state);
  return (
    <li className="glass elevation-2 flex items-center gap-3 rounded-xl p-3.5">
      <span className="bg-primary/10 text-primary grid size-10 shrink-0 place-items-center rounded-lg">
        <FileText className="size-5" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="line-clamp-1 text-sm font-medium">
            {file.original_filename}
          </span>
          <Badge
            variant="outline"
            title={status.hint}
            className={cn("shrink-0 text-[10px]", status.className)}
          >
            {status.label}
          </Badge>
        </div>
        <div className="text-muted-foreground mt-0.5 text-xs">
          {formatBytes(file.size_bytes)} · {file.chunk_count} chunks ·{" "}
          {file.indexed_at
            ? `indexed ${formatRelativeTime(file.indexed_at)}`
            : `uploaded ${formatRelativeTime(file.created_at)}`}
        </div>
        {repairable ? (
          <p className="text-muted-foreground mt-1 text-xs">
            {file.error_message ?? status.hint}
          </p>
        ) : null}
      </div>
      {repairable ? (
        <button
          type="button"
          onClick={onReindex}
          disabled={reindexing}
          aria-label={`Re-index ${file.original_filename}`}
          className="text-muted-foreground hover:text-primary shrink-0 rounded-lg p-2 transition-colors disabled:opacity-50"
        >
          {reindexing ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <RefreshCw className="size-4" />
          )}
        </button>
      ) : null}
      <button
        type="button"
        onClick={onDelete}
        aria-label={`Delete ${file.original_filename}`}
        className="text-muted-foreground shrink-0 rounded-lg p-2 transition-colors hover:text-red-500"
      >
        <Trash2 className="size-4" />
      </button>
    </li>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="glass elevation-2 rounded-xl p-3">
      <div className="text-lg leading-none font-semibold tabular-nums">
        {value}
      </div>
      <div className="text-muted-foreground mt-1 text-xs">{label}</div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="glass elevation-2 text-muted-foreground flex flex-col items-center gap-3 rounded-2xl px-6 py-12 text-center text-sm">
      <FileText className="size-6 opacity-60" />
      <span className="text-balance">
        No files yet. Upload a document to add it to GUMMY&apos;s knowledge.
      </span>
    </div>
  );
}
