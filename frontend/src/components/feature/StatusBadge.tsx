import {
  STATUS_CLASS,
  STATUS_LABEL,
  type FeatureStatus,
} from "@/config/registry";
import { cn } from "@/lib/utils";

/** Consistent status pill across feature surfaces. */
export function StatusBadge({
  status,
  label,
  className,
}: {
  status: FeatureStatus;
  label?: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium tracking-wide whitespace-nowrap",
        STATUS_CLASS[status],
        className,
      )}
    >
      {label ?? STATUS_LABEL[status]}
    </span>
  );
}
