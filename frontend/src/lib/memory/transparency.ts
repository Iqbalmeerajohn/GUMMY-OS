/**
 * "What GUMMY knows about you" — assembles a plain-language summary from stored
 * memories. No AI generation: it groups active memories by category and surfaces
 * the most important ones, so the user can see (and trust) what's remembered.
 */

import {
  MEMORY_CATEGORIES,
  getCategoryMeta,
  importanceWeight,
} from "@/config/memory";
import type { Memory } from "@/lib/memory/types";

export interface TransparencyGroup {
  category: string;
  label: string;
  icon: string;
  accent: string;
  count: number;
  /** Up to a few representative memories, most important first. */
  highlights: Memory[];
}

export interface Transparency {
  /** One-line headline, e.g. "GUMMY remembers 9 things about you". */
  headline: string;
  groups: TransparencyGroup[];
}

export function buildTransparency(
  memories: Memory[],
  highlightsPerGroup = 2,
): Transparency {
  const active = memories.filter((m) => m.status === "active");

  const groups: TransparencyGroup[] = MEMORY_CATEGORIES.map((cat) => {
    const inCat = active
      .filter((m) => m.category === cat.id)
      .sort(
        (a, b) =>
          importanceWeight(b.importance) - importanceWeight(a.importance) ||
          b.updated_at.localeCompare(a.updated_at),
      );
    return {
      category: cat.id,
      label: cat.label,
      icon: cat.icon,
      accent: cat.accent,
      count: inCat.length,
      highlights: inCat.slice(0, highlightsPerGroup),
    };
  })
    .filter((g) => g.count > 0)
    .sort((a, b) => b.count - a.count);

  const count = active.length;
  const headline =
    count === 0
      ? "GUMMY doesn't know anything about you yet."
      : `GUMMY remembers ${count} thing${count === 1 ? "" : "s"} about you across ${groups.length} ${groups.length === 1 ? "area" : "areas"}.`;

  return { headline, groups };
}

/** Helper re-export so callers don't reach into config for labels. */
export { getCategoryMeta };
