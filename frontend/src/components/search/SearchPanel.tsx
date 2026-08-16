"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Brain, MessageSquare, MessagesSquare, Search, X } from "lucide-react";

import { useAuth } from "@/components/auth/AuthProvider";
import { Skeleton } from "@/components/ui/skeleton";
import {
  type ConversationSearchHit,
  type MemorySearchHit,
  type MessageSearchHit,
  searchConversations,
  searchMemories,
  searchMessages,
} from "@/lib/api/resources";
import { formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const MIN_QUERY = 2;

/** A flattened, keyboard-navigable result and what opening it does. */
type FlatHit = {
  key: string;
  open: () => void;
};

/**
 * Unified search over conversations, messages, and memories — rendered inside
 * the shell's slide-over. Selecting a hit acts on the shell (switch the open
 * conversation, or reveal the memory panel) rather than navigating, because
 * GUMMY is a single surface.
 */
export function SearchPanel({
  onOpenConversation,
  onOpenMemories,
}: {
  onOpenConversation: (conversationId: string) => void;
  onOpenMemories: () => void;
}) {
  const { user } = useAuth();
  const [raw, setRaw] = useState("");
  const q = useDebounced(raw.trim(), 220);
  const enabled = !!user && q.length >= MIN_QUERY;
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const conversations = useQuery({
    queryKey: ["search", "conversations", q],
    queryFn: () => searchConversations(q),
    enabled,
    retry: false,
  });
  const messages = useQuery({
    queryKey: ["search", "messages", q],
    queryFn: () => searchMessages(q),
    enabled,
    retry: false,
  });
  const memories = useQuery({
    queryKey: ["search", "memories", q],
    queryFn: () => searchMemories(q),
    enabled,
    retry: false,
  });

  const convHits = conversations.data?.results ?? [];
  const msgHits = messages.data?.results ?? [];
  const memHits = memories.data?.results ?? [];

  // One ordered list across all groups so arrow-key navigation flows top-to-
  // bottom regardless of section. Cheap to recompute; no memo needed.
  const flat: FlatHit[] = [
    ...convHits.map((h) => ({
      key: `c:${h.conversation_id}`,
      open: () => onOpenConversation(h.conversation_id),
    })),
    ...msgHits.map((h) => ({
      key: `m:${h.message_id}`,
      open: () => onOpenConversation(h.conversation_id),
    })),
    ...memHits.map((h) => ({ key: `mem:${h.id}`, open: onOpenMemories })),
  ];

  const isLoading =
    enabled &&
    (conversations.isLoading || messages.isLoading || memories.isLoading);
  const total = convHits.length + msgHits.length + memHits.length;
  const noResults = enabled && !isLoading && total === 0;

  function onKeyDown(e: React.KeyboardEvent) {
    if (flat.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, flat.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      flat[active]?.open();
    }
  }

  // Map a group-local index to the flat index, for active-row highlighting.
  const convBase = 0;
  const msgBase = convHits.length;
  const memBase = convHits.length + msgHits.length;

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto p-4">
      <div className="glass elevation-2 mb-5 flex items-center gap-2.5 rounded-2xl px-4 py-3">
        <Search className="text-muted-foreground size-5 shrink-0" />
        <input
          ref={inputRef}
          value={raw}
          onChange={(e) => {
            setRaw(e.target.value);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
          // text-base (16px) prevents iOS Safari from zooming on focus.
          className="w-full bg-transparent text-base outline-none"
          placeholder="Search conversations, messages, and memories…"
          aria-label="Search everything"
          autoComplete="off"
        />
        {raw ? (
          <button
            onClick={() => {
              setRaw("");
              inputRef.current?.focus();
            }}
            aria-label="Clear search"
            className="text-muted-foreground hover:text-foreground grid size-8 shrink-0 place-items-center rounded-lg"
          >
            <X className="size-4" />
          </button>
        ) : null}
      </div>

      {!enabled ? (
        <InitialState short={raw.trim().length > 0} />
      ) : isLoading ? (
        <ResultsSkeleton />
      ) : noResults ? (
        <NoResults q={q} />
      ) : (
        <div className="space-y-7">
          <Group
            icon={<MessageSquare className="size-4" />}
            label="Conversations"
            count={convHits.length}
          >
            {convHits.map((h, i) => (
              <ConversationRow
                key={h.conversation_id}
                hit={h}
                term={q}
                active={active === convBase + i}
                onClick={() => onOpenConversation(h.conversation_id)}
              />
            ))}
          </Group>

          <Group
            icon={<MessagesSquare className="size-4" />}
            label="Messages"
            count={msgHits.length}
          >
            {msgHits.map((h, i) => (
              <MessageRow
                key={h.message_id}
                hit={h}
                term={q}
                active={active === msgBase + i}
                onClick={() => onOpenConversation(h.conversation_id)}
              />
            ))}
          </Group>

          <Group
            icon={<Brain className="size-4" />}
            label="Memories"
            count={memHits.length}
          >
            {memHits.map((h, i) => (
              <MemoryRow
                key={h.id}
                hit={h}
                term={q}
                active={active === memBase + i}
                onClick={onOpenMemories}
              />
            ))}
          </Group>
        </div>
      )}
    </div>
  );
}

// ── Debounce ──────────────────────────────────────────────────────────────────

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

// ── Grouped sections + rows ─────────────────────────────────────────────────

function Group({
  icon,
  label,
  count,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
  children: React.ReactNode;
}) {
  if (count === 0) return null;
  return (
    <section>
      <div className="text-muted-foreground mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-[0.12em] uppercase">
        {icon}
        {label}
        <span className="text-muted-foreground/70">({count})</span>
      </div>
      <ul className="space-y-1.5">{children}</ul>
    </section>
  );
}

const rowClass =
  "block w-full rounded-xl border border-border/50 bg-background/40 p-3 text-left transition-colors hover:border-primary/40 hover:bg-primary/5";

function ConversationRow({
  hit,
  term,
  active,
  onClick,
}: {
  hit: ConversationSearchHit;
  term: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <li>
      <button
        onClick={onClick}
        className={cn(rowClass, active && "border-primary/50 bg-primary/10")}
      >
        <span className="block truncate text-sm font-medium">
          <Highlighted
            text={hit.title ?? "Untitled conversation"}
            term={term}
          />
        </span>
        <span className="text-muted-foreground text-xs">
          {hit.message_count} message{hit.message_count === 1 ? "" : "s"}
          {hit.last_message_at
            ? ` · ${formatRelativeTime(hit.last_message_at)}`
            : ""}
        </span>
      </button>
    </li>
  );
}

function MessageRow({
  hit,
  term,
  active,
  onClick,
}: {
  hit: MessageSearchHit;
  term: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <li>
      <button
        onClick={onClick}
        className={cn(rowClass, active && "border-primary/50 bg-primary/10")}
      >
        <span className="text-muted-foreground mb-0.5 block truncate text-[11px] font-medium tracking-wide uppercase">
          {hit.role === "assistant" ? "GUMMY" : "You"}
          {hit.conversation_title ? ` · ${hit.conversation_title}` : ""}
        </span>
        <span className="line-clamp-2 text-sm">
          <Highlighted text={hit.content} term={term} />
        </span>
      </button>
    </li>
  );
}

function MemoryRow({
  hit,
  term,
  active,
  onClick,
}: {
  hit: MemorySearchHit;
  term: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <li>
      <button
        onClick={onClick}
        className={cn(rowClass, active && "border-primary/50 bg-primary/10")}
      >
        <span className="text-primary/80 mb-0.5 block text-[11px] font-medium tracking-wide uppercase">
          {hit.category}
        </span>
        <span className="line-clamp-2 text-sm">
          <Highlighted text={hit.content} term={term} />
        </span>
      </button>
    </li>
  );
}

/** Case-insensitive match highlighting (no dangerouslySetInnerHTML). */
function Highlighted({ text, term }: { text: string; term: string }) {
  const i = term ? text.toLowerCase().indexOf(term.toLowerCase()) : -1;
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

// ── States ──────────────────────────────────────────────────────────────────

function InitialState({ short }: { short: boolean }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-16 text-center">
      <Search className="text-muted-foreground/40 size-7" />
      <p className="text-sm font-medium">
        {short ? "Keep typing…" : "Search everything GUMMY knows"}
      </p>
      <p className="text-muted-foreground text-xs text-balance">
        Find any conversation, message, or memory — type at least {MIN_QUERY}{" "}
        characters.
      </p>
    </div>
  );
}

function NoResults({ q }: { q: string }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-16 text-center">
      <Search className="text-muted-foreground/40 size-7" />
      <p className="text-sm font-medium">No results for “{q}”.</p>
      <p className="text-muted-foreground text-xs">
        Try different words, or fewer of them.
      </p>
    </div>
  );
}

function ResultsSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-16 w-full rounded-xl" />
      ))}
    </div>
  );
}
