import { getStatusMeta } from "@/config/goals";
import type { GoalStatus } from "@/lib/api/resources";
import { cn } from "@/lib/utils";

/** A small pill reflecting a goal's lifecycle status (active/completed/archived). */
export function GoalStatusBadge({
  status,
  className,
}: {
  status: GoalStatus;
  className?: string;
}) {
  const meta = getStatusMeta(status);
  return (
    <span
      className={cn(
        "inline-flex h-5 w-fit shrink-0 items-center rounded-full border px-2 text-[10px] font-medium",
        meta.badge,
        className,
      )}
    >
      {meta.label}
    </span>
  );
}
