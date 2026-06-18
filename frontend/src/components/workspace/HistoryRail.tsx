"use client";

import { useMemo, useRef, useState } from "react";
import { MoreVertical, Pin, Plus, Search } from "lucide-react";
import { toast } from "sonner";

import { LivingOrb } from "@/components/brand/LivingOrb";
import { ConversationMenu } from "@/components/workspace/ConversationMenu";
import { buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import type { ConversationItem } from "@/lib/api/resources";
import {
  useConversations,
  useDeleteConversation,
  useUpdateConversation,
} from "@/lib/hooks/useChat";
import { formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type Tab = "active" | "archived";

/** Conversation history + search + management (the left rail). */
export function HistoryRail({
  activeId,
  onSelect,
  onNew,
}: {
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const { data, isLoading } = useConversations();
  const update = useUpdateConversation();
  const remove = useDeleteConversation();

  const [q, setQ] = useState("");
  const [tab, setTab] = useState<Tab>("active");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ConversationItem | null>(
    null,
  );

  const all = useMemo(() => data?.items ?? [], [data]);
  const term = q.trim().toLowerCase();

  const filtered = useMemo(
    () =>
      all.filter((c) => {
        const inTab =
          tab === "archived" ? c.status === "archived" : c.status !== "archived";
        const title = (c.title ?? "Untitled conversation").toLowerCase();
        return inTab && (!term || title.includes(term));
      }),
    [all, tab, term],
  );

  const pinned = filtered.filter((c) => c.pinned);
  const rest = filtered.filter((c) => !c.pinned);

  function togglePin(c: ConversationItem) {
    update.mutate({ id: c.id, body: { pinned: !c.pinned } });
  }
  function toggleArchive(c: ConversationItem) {
    update.mutate({
      id: c.id,
      body: { status: c.status === "archived" ? "active" : "archived" },
    });
    toast.success(c.status === "archived" ? "Restored." : "Archived.");
  }
  function rename(id: string, title: string) {
    const next = title.trim();
    setRenamingId(null);
    if (next) update.mutate({ id, body: { title: next } });
  }
  function confirmDelete() {
    if (!deleteTarget) return;
    remove.mutate(deleteTarget.id);
    toast.success("Conversation deleted.");
    setDeleteTarget(null);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="space-y-3 p-3">
        <button
          onClick={onNew}
          className={cn(buttonVariants({ size: "sm" }), "w-full gap-1.5")}
        >
          <Plus className="size-4" />
          New conversation
        </button>
        <div className="relative">
          <Search className="text-muted-foreground absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search conversations"
            className="border-input focus-visible:border-primary/50 focus-visible:ring-primary/30 h-8 w-full rounded-lg border bg-transparent pr-2 pl-8 text-sm outline-none focus-visible:ring-2"
          />
        </div>
        <div className="bg-muted/60 inline-flex w-full rounded-lg p-[3px] text-xs font-medium">
          {(["active", "archived"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "flex-1 rounded-md py-1 capitalize transition-colors",
                tab === t
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {isLoading ? (
          <SidebarSkeleton />
        ) : filtered.length === 0 ? (
          <EmptyRail tab={tab} searching={!!term} />
        ) : (
          <div className="space-y-3">
            {pinned.length > 0 && tab === "active" ? (
              <Section label="Pinned">
                {pinned.map((c) => (
                  <ConversationRow
                    key={c.id}
                    c={c}
                    active={c.id === activeId}
                    renaming={renamingId === c.id}
                    highlight={term}
                    onSelect={() => onSelect(c.id)}
                    onPin={() => togglePin(c)}
                    onRename={() => setRenamingId(c.id)}
                    onRenameCommit={(t) => rename(c.id, t)}
                    onRenameCancel={() => setRenamingId(null)}
                    onArchive={() => toggleArchive(c)}
                    onDelete={() => setDeleteTarget(c)}
                  />
                ))}
              </Section>
            ) : null}
            <Section label={pinned.length > 0 && tab === "active" ? "All" : null}>
              {rest.map((c) => (
                <ConversationRow
                  key={c.id}
                  c={c}
                  active={c.id === activeId}
                  renaming={renamingId === c.id}
                  highlight={term}
                  onSelect={() => onSelect(c.id)}
                  onPin={() => togglePin(c)}
                  onRename={() => setRenamingId(c.id)}
                  onRenameCommit={(t) => rename(c.id, t)}
                  onRenameCancel={() => setRenamingId(null)}
                  onArchive={() => toggleArchive(c)}
                  onDelete={() => setDeleteTarget(c)}
                />
              ))}
            </Section>
          </div>
        )}
      </div>

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
      >
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete conversation?</DialogTitle>
            <DialogDescription>
              This action cannot be undone. “
              {deleteTarget?.title ?? "Untitled conversation"}” and its messages
              will be permanently removed.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose
              render={
                <button className={cn(buttonVariants({ variant: "outline" }))} />
              }
            >
              Cancel
            </DialogClose>
            <button
              onClick={confirmDelete}
              className={cn(buttonVariants({ variant: "destructive" }))}
            >
              Delete
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Section({
  label,
  children,
}: {
  label: string | null;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      {label ? (
        <p className="text-muted-foreground/80 px-3 pt-1 text-[10px] font-semibold tracking-[0.18em] uppercase">
          {label}
        </p>
      ) : null}
      <ul className="space-y-0.5">{children}</ul>
    </div>
  );
}

function ConversationRow({
  c,
  active,
  renaming,
  highlight,
  onSelect,
  onPin,
  onRename,
  onRenameCommit,
  onRenameCancel,
  onArchive,
  onDelete,
}: {
  c: ConversationItem;
  active: boolean;
  renaming: boolean;
  highlight: string;
  onSelect: () => void;
  onPin: () => void;
  onRename: () => void;
  onRenameCommit: (title: string) => void;
  onRenameCancel: () => void;
  onArchive: () => void;
  onDelete: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const title = c.title ?? "Untitled conversation";

  if (renaming) {
    return (
      <li>
        <input
          ref={inputRef}
          autoFocus
          defaultValue={title}
          onBlur={(e) => onRenameCommit(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onRenameCommit(e.currentTarget.value);
            if (e.key === "Escape") onRenameCancel();
          }}
          className="border-primary/50 ring-primary/30 w-full rounded-lg border bg-transparent px-3 py-2 text-sm outline-none ring-2"
        />
      </li>
    );
  }

  return (
    <li>
      <div
        onClick={onSelect}
        className={cn(
          "group relative flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 transition-colors",
          active
            ? "bg-primary/10 ring-primary/20 ring-1"
            : "hover:bg-muted/60",
        )}
      >
        {c.pinned ? (
          <Pin className="text-primary size-3 shrink-0 -rotate-45" />
        ) : null}
        <div className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">
            <Highlighted text={title} term={highlight} />
          </span>
          <span className="text-muted-foreground text-xs">
            {formatRelativeTime(c.last_message_at) || "New"}
          </span>
        </div>
        {/* Three-dot menu — always visible on touch (no hover); hover-revealed
            on desktop. Stays visible while open on any size. */}
        <div
          className={cn(
            "shrink-0 transition-opacity",
            "max-lg:opacity-100 lg:opacity-0 lg:group-hover:opacity-100",
            "data-[open]:opacity-100",
          )}
        >
          <ConversationMenu
            pinned={c.pinned}
            archived={c.status === "archived"}
            onPin={onPin}
            onRename={onRename}
            onArchive={onArchive}
            onDelete={onDelete}
            trigger={
              <span className="text-muted-foreground hover:bg-background hover:text-foreground grid size-11 place-items-center rounded-md lg:size-8">
                <MoreVertical className="size-5 lg:size-4" />
              </span>
            }
          />
        </div>
      </div>
    </li>
  );
}

/** Highlights search matches without dangerouslySetInnerHTML. */
function Highlighted({ text, term }: { text: string; term: string }) {
  if (!term) return <>{text}</>;
  const i = text.toLowerCase().indexOf(term);
  if (i === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, i)}
      <mark className="bg-primary/25 text-foreground rounded-sm px-0.5">
        {text.slice(i, i + term.length)}
      </mark>
      {text.slice(i + term.length)}
    </>
  );
}

function SidebarSkeleton() {
  return (
    <div className="space-y-1.5 px-1">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-center gap-2 px-2 py-1.5">
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-3/4 rounded" />
            <Skeleton className="h-2.5 w-1/3 rounded" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyRail({ tab, searching }: { tab: Tab; searching: boolean }) {
  if (searching) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
        <Search className="text-muted-foreground/50 size-5" />
        <p className="text-sm font-medium">Nothing found.</p>
        <p className="text-muted-foreground text-xs">Try another search.</p>
      </div>
    );
  }
  if (tab === "archived") {
    return (
      <p className="text-muted-foreground px-3 py-10 text-center text-xs text-balance">
        No archived conversations.
      </p>
    );
  }
  return (
    <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
      <LivingOrb size={56} state="idle" />
      <p className="text-sm font-medium">Start your first conversation.</p>
      <p className="text-muted-foreground text-xs text-balance">
        Ask GUMMY anything — it remembers what matters about you.
      </p>
    </div>
  );
}
