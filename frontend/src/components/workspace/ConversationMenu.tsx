"use client";

import {
  Archive,
  ArchiveRestore,
  Pencil,
  Pin,
  PinOff,
  Trash2,
} from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

/**
 * The GUMMY conversation menu — a glassy, emerald-lit action surface. Not a
 * clone of ChatGPT/Claude: soft glow, rounded, accent-coded actions (emerald
 * pin, neutral archive, red delete), with the primitive's scale/fade motion.
 */
export function ConversationMenu({
  pinned,
  archived,
  onPin,
  onRename,
  onArchive,
  onDelete,
  trigger,
}: {
  pinned: boolean;
  archived: boolean;
  onPin: () => void;
  onRename: () => void;
  onArchive: () => void;
  onDelete: () => void;
  trigger: React.ReactNode;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button
            type="button"
            aria-label="Conversation actions"
            onClick={(e) => e.stopPropagation()}
          />
        }
      >
        {trigger}
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={6}
        className={cn(
          // Glass morphism + soft emerald glow ring + rounded corners.
          "glass border-primary/15 ring-primary/10 w-52 rounded-2xl border p-1.5",
          "shadow-[0_8px_40px_-12px_var(--color-primary)]/30 backdrop-blur-xl",
        )}
      >
        <MenuRow
          icon={pinned ? <PinOff className="size-4" /> : <Pin className="size-4" />}
          label={pinned ? "Unpin conversation" : "Pin conversation"}
          accent="emerald"
          onClick={onPin}
        />
        <MenuRow
          icon={<Pencil className="size-4" />}
          label="Rename"
          accent="neutral"
          onClick={onRename}
        />
        <DropdownMenuSeparator className="bg-border/60" />
        <MenuRow
          icon={
            archived ? (
              <ArchiveRestore className="size-4" />
            ) : (
              <Archive className="size-4" />
            )
          }
          label={archived ? "Unarchive" : "Archive"}
          accent="neutral"
          onClick={onArchive}
        />
        <MenuRow
          icon={<Trash2 className="size-4" />}
          label="Delete"
          accent="danger"
          onClick={onDelete}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function MenuRow({
  icon,
  label,
  accent,
  hint,
  disabled,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  accent: "emerald" | "neutral" | "danger";
  hint?: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <DropdownMenuItem
      disabled={disabled}
      onClick={() => onClick()}
      className={cn(
        "flex min-h-11 items-center gap-2 rounded-xl px-2.5 py-2 text-sm transition-colors sm:min-h-9",
        accent === "emerald" &&
          "text-primary focus:bg-primary/12 focus:text-primary",
        accent === "neutral" && "focus:bg-muted/70",
        accent === "danger" &&
          "text-destructive focus:bg-destructive/12 focus:text-destructive",
      )}
    >
      {icon}
      <span className="flex-1">{label}</span>
      {hint ? (
        <span className="text-muted-foreground/70 text-[10px] font-medium tracking-wide uppercase">
          {hint}
        </span>
      ) : null}
    </DropdownMenuItem>
  );
}
