"use client";

import { useState } from "react";
import { Archive, ArchiveRestore, History, Pencil, Trash2 } from "lucide-react";

import { CategoryChip, ImportanceBadge } from "@/components/memory/MemoryBadges";
import { ConfirmDialog } from "@/components/memory/ConfirmDialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { getSourceLabel } from "@/config/memory";
import { formatFullDate } from "@/lib/format";
import type { Memory } from "@/lib/memory/types";

/** Memory detail view (Deliverable 6) + management actions (Deliverable 7). */
export function MemoryDetailDialog({
  memory,
  onOpenChange,
  onEdit,
  onArchive,
  onRestore,
  onDelete,
}: {
  /** The memory to show, or null when closed. */
  memory: Memory | null;
  onOpenChange: (open: boolean) => void;
  onEdit: (memory: Memory) => void;
  onArchive: (id: string) => void;
  onRestore: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <Dialog open={!!memory} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        {memory ? (
          <>
            <DialogHeader>
              <div className="flex flex-wrap items-center gap-1.5">
                <CategoryChip category={memory.category} />
                <ImportanceBadge importance={memory.importance} />
                {memory.status === "archived" ? (
                  <span className="text-muted-foreground border-border rounded-full border px-2 py-0.5 text-[10px] font-medium">
                    Archived
                  </span>
                ) : null}
              </div>
              <DialogTitle className="sr-only">Memory detail</DialogTitle>
              <DialogDescription className="sr-only">
                Full memory content, metadata, and version history.
              </DialogDescription>
            </DialogHeader>

            <p className="text-sm leading-relaxed text-balance">
              {memory.content}
            </p>

            <dl className="border-border/60 grid grid-cols-2 gap-x-4 gap-y-2.5 rounded-xl border p-3 text-xs">
              <Meta label="Source" value={getSourceLabel(memory.source)} />
              <Meta
                label="Created"
                value={formatFullDate(memory.created_at)}
              />
              <Meta
                label="Last updated"
                value={formatFullDate(memory.updated_at)}
              />
              <Meta
                label="Revisions"
                value={String(memory.versions.length)}
              />
            </dl>

            <VersionHistory memory={memory} />

            <div className="flex flex-wrap gap-2 pt-1">
              <Button size="sm" variant="outline" onClick={() => onEdit(memory)}>
                <Pencil className="size-3.5" />
                Edit
              </Button>
              {memory.status === "archived" ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    onRestore(memory.id);
                    onOpenChange(false);
                  }}
                >
                  <ArchiveRestore className="size-3.5" />
                  Restore
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setConfirmArchive(true)}
                >
                  <Archive className="size-3.5" />
                  Archive
                </Button>
              )}
              <Button
                size="sm"
                variant="destructive"
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 className="size-3.5" />
                Delete
              </Button>
            </div>

            <ConfirmDialog
              open={confirmArchive}
              onOpenChange={setConfirmArchive}
              title="Archive this memory?"
              description="GUMMY will stop using it, but you can restore it anytime."
              confirmLabel="Archive"
              onConfirm={() => {
                onArchive(memory.id);
                onOpenChange(false);
              }}
            />
            <ConfirmDialog
              open={confirmDelete}
              onOpenChange={setConfirmDelete}
              title="Delete this memory?"
              description="This permanently removes the memory. This can't be undone."
              confirmLabel="Delete"
              destructive
              onConfirm={() => {
                onDelete(memory.id);
                onOpenChange(false);
              }}
            />
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}

/** Version history (Deliverable 6). Architecture supports future versioning. */
function VersionHistory({ memory }: { memory: Memory }) {
  return (
    <div className="space-y-2">
      <span className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium tracking-[0.12em] uppercase">
        <History className="size-3.5" />
        Version history
      </span>
      {memory.versions.length === 0 ? (
        <p className="text-muted-foreground text-xs text-balance">
          No earlier versions yet. Edits will be tracked here.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {[...memory.versions].reverse().map((v, i) => (
            <li
              key={`${v.changed_at}-${i}`}
              className="border-border/50 bg-background/40 rounded-lg border p-2.5 text-xs"
            >
              <span className="text-muted-foreground block text-[10px]">
                {formatFullDate(v.changed_at)}
              </span>
              <span className="line-clamp-2">{v.content}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
