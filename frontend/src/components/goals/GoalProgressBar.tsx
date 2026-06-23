import { cn } from "@/lib/utils";

/**
 * A labeled progress bar for a goal. ``value`` is a 0–100 percentage; when a
 * goal has milestones this is milestone-derived, otherwise it is the manually
 * set value. Renders a subtle track + animated fill, matching the dashboard.
 */
export function GoalProgressBar({
  value,
  showLabel = true,
  className,
}: {
  value: number;
  showLabel?: boolean;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, Math.round(value)));
  const complete = pct >= 100;
  return (
    <div className={cn("w-full", className)}>
      {showLabel ? (
        <div className="text-muted-foreground mb-1 flex items-center justify-between text-[11px]">
          <span>Progress</span>
          <span className="text-foreground font-medium tabular-nums">
            {pct}%
          </span>
        </div>
      ) : null}
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        className="bg-muted h-2 overflow-hidden rounded-full"
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-700",
            complete ? "bg-emerald-500" : "bg-primary",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
