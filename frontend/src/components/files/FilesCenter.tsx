"use client";

import { useRef, useState } from "react";
import { FileText, Loader2, Trash2, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useFileActions,
  useFilesQuery,
  useFileStats,
} from "@/lib/files/useFiles";
import type { FileItem, FileProcessingStatus } from "@/lib/api/resources";
import { formatBytes, formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

// Mirrors the backend's SUPPORTED_FILE_MIME_TYPES (M6 MVP + cheap extras).
const ACCEPT = ".pdf,.txt,.md,.markdown,.docx,.csv,.xlsx";

const STATUS_META: Record<
  FileProcessingStatus,
  { label: string; className: string }
> = {
  completed: {
    label: "Ready",
    className: "border-primary/40 bg-primary/15 text-primary",
  },
  processing: {
    label: "Processing",
    className: "border-amber-500/40 bg-amber-500/15 text-amber-500",
  },
  pending: {
    label: "Pending",
    className: "border-border text-muted-foreground",
  },
  failed: {
    label: "Failed",
    className: "border-red-500/40 bg-red-500/15 text-red-500",
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
        <Stat
          label="Ready"
          value={
            items.filter((f) => f.processing_status === "completed").length
          }
        />
      </div>

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
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function FileRow({ file, onDelete }: { file: FileItem; onDelete: () => void }) {
  const status = STATUS_META[file.processing_status];
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
            className={cn("shrink-0 text-[10px]", status.className)}
          >
            {status.label}
          </Badge>
        </div>
        <div className="text-muted-foreground mt-0.5 text-xs">
          {formatBytes(file.size_bytes)} · {file.chunk_count} chunks ·{" "}
          {formatRelativeTime(file.created_at)}
        </div>
      </div>
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
