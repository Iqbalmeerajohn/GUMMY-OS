import { createElement } from "react";

import {
  getCategoryMeta,
  getImportanceMeta,
  type MemoryImportance,
} from "@/config/memory";
import { getIcon } from "@/lib/icons";
import { cn } from "@/lib/utils";

/** Importance pill — visual only (Deliverable 5). */
export function ImportanceBadge({
  importance,
  className,
}: {
  importance: MemoryImportance;
  className?: string;
}) {
  const meta = getImportanceMeta(importance);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium tracking-wide whitespace-nowrap",
        meta.badge,
        className,
      )}
    >
      <span
        aria-hidden
        className="size-1.5 rounded-full bg-current opacity-80"
      />
      {meta.label}
    </span>
  );
}

/** Category chip with its icon + accent. */
export function CategoryChip({
  category,
  className,
  withIcon = true,
}: {
  category: string;
  className?: string;
  withIcon?: boolean;
}) {
  const meta = getCategoryMeta(category);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium whitespace-nowrap",
        meta.accent,
        className,
      )}
    >
      {withIcon
        ? createElement(getIcon(meta.icon), { className: "size-3" })
        : null}
      {meta.label}
    </span>
  );
}
