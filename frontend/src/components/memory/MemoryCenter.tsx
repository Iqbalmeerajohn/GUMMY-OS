"use client";

import { useMemo, useState } from "react";
import { Brain, Plus, Search } from "lucide-react";
import { toast } from "sonner";

import { MemoryCard } from "@/components/memory/MemoryCard";
import { MemoryDetailDialog } from "@/components/memory/MemoryDetailDialog";
import { MemoryFormDialog } from "@/components/memory/MemoryFormDialog";
import { MemoryTransparency } from "@/components/memory/MemoryTransparency";
import { Reveal } from "@/components/motion/Reveal";
import { Stagger, StaggerItem } from "@/components/motion/Stagger";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  MEMORY_CATEGORIES,
  type MemoryCategory,
} from "@/config/memory";
import { getIcon } from "@/lib/icons";
import { cn } from "@/lib/utils";
import type { MemoryDraft } from "@/lib/memory/store";
import type {
  Memory,
  MemorySort,
  MemoryStatus,
} from "@/lib/memory/types";
import {
  useMemory,
  useMemoryActions,
  useMemoryList,
  useMemoriesReady,
  useMemoryStats,
} from "@/lib/memory/useMemory";

type CategoryFilter = MemoryCategory | "all";

const SORT_LABELS: Record<MemorySort, string> = {
  newest: "Newest first",
  oldest: "Oldest first",
  updated: "Recently updated",
};

/** Memory Center (Deliverable 1) — the main memory management experience. */
export function MemoryCenter() {
  const ready = useMemoriesReady();
  const stats = useMemoryStats();
  const actions = useMemoryActions();

  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<CategoryFilter>("all");
  const [status, setStatus] = useState<MemoryStatus>("active");
  const [sort, setSort] = useState<MemorySort>("newest");

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [formMode, setFormMode] = useState<"add" | "edit">("add");
  const [formInitial, setFormInitial] = useState<Memory | null>(null);

  const query = useMemo(
    () => ({ query: search, category, status, sort }),
    [search, category, status, sort],
  );
  const memories = useMemoryList(query);
  const selected = useMemory(selectedId);

  const hasAny = stats.total > 0;

  function openAdd() {
    setFormMode("add");
    setFormInitial(null);
    setFormOpen(true);
  }

  function openEdit(memory: Memory) {
    setSelectedId(null);
    setFormMode("edit");
    setFormInitial(memory);
    setFormOpen(true);
  }

  function handleSubmit(draft: MemoryDraft) {
    if (formMode === "add") {
      actions.add(draft);
      toast.success("Memory saved.");
    } else if (formInitial) {
      actions.update(formInitial.id, draft);
      toast.success("Memory updated.");
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <Reveal>
        <Header
          total={stats.active}
          archived={stats.archived}
          onAdd={openAdd}
        />
      </Reveal>

      {ready && hasAny ? (
        <Reveal delay={0.04}>
          <MemoryTransparency
            onSelectCategory={(c) => {
              setCategory(c);
              setStatus("active");
            }}
          />
        </Reveal>
      ) : null}

      <Reveal delay={0.06}>
        <Controls
          search={search}
          onSearch={setSearch}
          sort={sort}
          onSort={setSort}
          status={status}
          onStatus={setStatus}
        />
      </Reveal>

      <Reveal delay={0.08}>
        <Filters
          category={category}
          onCategory={setCategory}
          counts={stats.byCategory}
        />
      </Reveal>

      {!ready ? (
        <LoadingGrid />
      ) : memories.length === 0 ? (
        <EmptyState
          hasAny={hasAny}
          filtered={hasAny}
          onAdd={openAdd}
          onClear={() => {
            setSearch("");
            setCategory("all");
            setStatus("active");
          }}
          onRestoreDemo={() => {
            actions.reset();
            toast.success("Demo memories restored.");
          }}
        />
      ) : (
        <Stagger className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {memories.map((m) => (
            <StaggerItem key={m.id}>
              <MemoryCard memory={m} onOpen={setSelectedId} />
            </StaggerItem>
          ))}
        </Stagger>
      )}

      <MemoryDetailDialog
        memory={selected ?? null}
        onOpenChange={(open) => {
          if (!open) setSelectedId(null);
        }}
        onEdit={openEdit}
        onArchive={(id) => {
          actions.archive(id);
          toast.success("Memory archived.");
        }}
        onRestore={(id) => {
          actions.restore(id);
          toast.success("Memory restored.");
        }}
        onDelete={(id) => {
          actions.remove(id);
          toast.success("Memory deleted.");
        }}
      />

      <MemoryFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        mode={formMode}
        initial={formInitial}
        onSubmit={handleSubmit}
      />
    </div>
  );
}

function Header({
  total,
  archived,
  onAdd,
}: {
  total: number;
  archived: number;
  onAdd: () => void;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="text-primary/85 text-xs font-medium tracking-[0.28em] uppercase">
          Memory
        </p>
        <h1 className="font-heading mt-2 flex items-center gap-2.5 text-3xl font-semibold tracking-tight sm:text-4xl">
          <Brain className="text-primary size-7" />
          Memory Center
        </h1>
        <p className="text-muted-foreground mt-2 max-w-2xl text-sm">
          Everything GUMMY remembers about you — transparent, searchable, and
          yours to manage.
          <span className="text-muted-foreground/80">
            {" "}
            {total} active{archived ? ` · ${archived} archived` : ""}.
          </span>
        </p>
      </div>
      <Button onClick={onAdd}>
        <Plus className="size-4" />
        Add memory
      </Button>
    </div>
  );
}

function Controls({
  search,
  onSearch,
  sort,
  onSort,
  status,
  onStatus,
}: {
  search: string;
  onSearch: (v: string) => void;
  sort: MemorySort;
  onSort: (v: MemorySort) => void;
  status: MemoryStatus;
  onStatus: (v: MemoryStatus) => void;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <div className="relative flex-1">
        <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2" />
        <input
          type="search"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search memories…"
          aria-label="Search memories"
          className="border-input focus-visible:border-ring focus-visible:ring-ring/50 dark:bg-input/30 h-9 w-full rounded-lg border bg-transparent pr-3 pl-8 text-sm outline-none focus-visible:ring-3"
        />
      </div>
      <div className="flex items-center gap-2">
        <Segmented
          options={[
            { value: "active", label: "Active" },
            { value: "archived", label: "Archived" },
          ]}
          value={status}
          onChange={(v) => onStatus(v as MemoryStatus)}
        />
        <select
          value={sort}
          onChange={(e) => onSort(e.target.value as MemorySort)}
          aria-label="Sort memories"
          className="border-input dark:bg-input/30 h-9 rounded-lg border bg-transparent px-2.5 text-sm outline-none"
        >
          {(Object.keys(SORT_LABELS) as MemorySort[]).map((s) => (
            <option key={s} value={s} className="bg-popover">
              {SORT_LABELS[s]}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

function Segmented({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="bg-muted inline-flex h-9 items-center rounded-lg p-[3px]">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={cn(
            "h-full rounded-md px-2.5 text-xs font-medium transition-colors",
            value === o.value
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Filters({
  category,
  onCategory,
  counts,
}: {
  category: CategoryFilter;
  onCategory: (c: CategoryFilter) => void;
  counts: Record<string, number>;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <FilterChip
        active={category === "all"}
        onClick={() => onCategory("all")}
      >
        All
      </FilterChip>
      {MEMORY_CATEGORIES.map((c) => {
        const Icon = getIcon(c.icon);
        return (
          <FilterChip
            key={c.id}
            active={category === c.id}
            onClick={() => onCategory(c.id)}
          >
            <Icon className="size-3" />
            {c.label}
            {counts[c.id] ? (
              <span className="text-muted-foreground/80 text-[10px]">
                {counts[c.id]}
              </span>
            ) : null}
          </FilterChip>
        );
      })}
    </div>
  );
}

function FilterChip({
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
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
        active
          ? "border-primary/40 bg-primary/15 text-primary"
          : "border-border text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function LoadingGrid() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-32 w-full rounded-2xl" />
      ))}
    </div>
  );
}

function EmptyState({
  hasAny,
  filtered,
  onAdd,
  onClear,
  onRestoreDemo,
}: {
  hasAny: boolean;
  filtered: boolean;
  onAdd: () => void;
  onClear: () => void;
  onRestoreDemo: () => void;
}) {
  if (hasAny && filtered) {
    return (
      <div className="glass flex flex-col items-center gap-3 rounded-2xl p-10 text-center">
        <Search className="text-muted-foreground size-6 opacity-60" />
        <p className="text-sm font-medium">No memories match your filters.</p>
        <p className="text-muted-foreground max-w-sm text-sm text-balance">
          Try a different search, category, or switch between active and
          archived.
        </p>
        <Button variant="outline" size="sm" onClick={onClear}>
          Clear filters
        </Button>
      </div>
    );
  }

  return (
    <div className="glass flex flex-col items-center gap-3 rounded-2xl p-12 text-center">
      <span className="bg-accent text-primary grid size-12 place-items-center rounded-2xl">
        <Brain className="size-6" />
      </span>
      <p className="text-base font-medium">No memories yet.</p>
      <p className="text-muted-foreground max-w-sm text-sm text-balance">
        Teach GUMMY something to get started — it&apos;ll remember what matters
        about you across conversations.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <Button onClick={onAdd}>
          <Plus className="size-4" />
          Add your first memory
        </Button>
        <Button variant="ghost" size="sm" onClick={onRestoreDemo}>
          Restore demo memories
        </Button>
      </div>
    </div>
  );
}
