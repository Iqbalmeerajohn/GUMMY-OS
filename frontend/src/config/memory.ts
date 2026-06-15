/**
 * GUMMY Memory Registry — the SINGLE SOURCE OF TRUTH for memory taxonomy.
 *
 * Categories, importance levels, and sources are defined here so every memory
 * surface (Memory Center, dashboard widget, workspace hub, transparency view)
 * stays consistent. Add a category here and filters/badges/colors update
 * everywhere — there are no duplicated lists.
 *
 * Icons are referenced by name (string) and resolved via `lib/icons`, keeping
 * this data serializable and consistent with the feature registry.
 *
 * Phase 5 seam: new categories can be appended freely; retrieval ranking will
 * later read `importance` ordering and category weighting from here.
 */

// ── Categories ────────────────────────────────────────────────────────────────

export type MemoryCategory =
  | "career"
  | "projects"
  | "learning"
  | "goals"
  | "preferences"
  | "business"
  | "personal";

export interface MemoryCategoryMeta {
  id: MemoryCategory;
  label: string;
  /** Icon name resolved via lib/icons. */
  icon: string;
  /** Tailwind classes for the category accent (badge / chip). */
  accent: string;
  /** One-line description used in transparency + empty hints. */
  blurb: string;
}

export const MEMORY_CATEGORIES: MemoryCategoryMeta[] = [
  {
    id: "career",
    label: "Career",
    icon: "Briefcase",
    accent: "bg-sky-400/15 text-sky-300 border-sky-400/30",
    blurb: "Roles, applications, and professional moves.",
  },
  {
    id: "projects",
    label: "Projects",
    icon: "FolderKanban",
    accent: "bg-violet-400/15 text-violet-300 border-violet-400/30",
    blurb: "What you're building and shipping.",
  },
  {
    id: "learning",
    label: "Learning",
    icon: "GraduationCap",
    accent: "bg-emerald-400/15 text-emerald-300 border-emerald-400/30",
    blurb: "Skills, topics, and study in progress.",
  },
  {
    id: "goals",
    label: "Goals",
    icon: "Target",
    accent: "bg-amber-400/15 text-amber-300 border-amber-400/30",
    blurb: "What you're working toward.",
  },
  {
    id: "preferences",
    label: "Preferences",
    icon: "SlidersHorizontal",
    accent: "bg-primary/15 text-primary border-primary/30",
    blurb: "How you like GUMMY to work with you.",
  },
  {
    id: "business",
    label: "Business",
    icon: "Building2",
    accent: "bg-rose-400/15 text-rose-300 border-rose-400/30",
    blurb: "Ventures, operations, and decisions.",
  },
  {
    id: "personal",
    label: "Personal",
    icon: "UserCircle",
    accent: "bg-teal-400/15 text-teal-300 border-teal-400/30",
    blurb: "About you, your life, and the people in it.",
  },
];

const CATEGORY_BY_ID = new Map(MEMORY_CATEGORIES.map((c) => [c.id, c]));

export function getCategoryMeta(id: string): MemoryCategoryMeta {
  return (
    CATEGORY_BY_ID.get(id as MemoryCategory) ?? {
      id: "personal",
      label: id ? id[0].toUpperCase() + id.slice(1) : "Other",
      icon: "Brain",
      accent: "bg-muted text-muted-foreground border-border",
      blurb: "",
    }
  );
}

export function isMemoryCategory(value: string): value is MemoryCategory {
  return CATEGORY_BY_ID.has(value as MemoryCategory);
}

// ── Importance ────────────────────────────────────────────────────────────────

export type MemoryImportance = "low" | "medium" | "high" | "critical";

export interface MemoryImportanceMeta {
  id: MemoryImportance;
  label: string;
  /** Display order weight (higher = more important). */
  weight: number;
  /** Tailwind classes for the importance badge. */
  badge: string;
  /** Representative score (0–1) — the backend persists a float; UI maps to a level. */
  score: number;
}

export const MEMORY_IMPORTANCE: MemoryImportanceMeta[] = [
  {
    id: "low",
    label: "Low",
    weight: 0,
    badge: "bg-muted text-muted-foreground border-border",
    score: 0.25,
  },
  {
    id: "medium",
    label: "Medium",
    weight: 1,
    badge: "bg-sky-400/15 text-sky-300 border-sky-400/30",
    score: 0.5,
  },
  {
    id: "high",
    label: "High",
    weight: 2,
    badge: "bg-amber-400/15 text-amber-300 border-amber-400/30",
    score: 0.75,
  },
  {
    id: "critical",
    label: "Critical",
    weight: 3,
    badge: "bg-rose-400/15 text-rose-300 border-rose-400/30",
    score: 1,
  },
];

const IMPORTANCE_BY_ID = new Map(MEMORY_IMPORTANCE.map((i) => [i.id, i]));

export function getImportanceMeta(id: MemoryImportance): MemoryImportanceMeta {
  return IMPORTANCE_BY_ID.get(id) ?? MEMORY_IMPORTANCE[0];
}

/** Map a backend importance_score (0–1 float) to a UI level. */
export function importanceFromScore(score: number): MemoryImportance {
  if (score >= 0.85) return "critical";
  if (score >= 0.6) return "high";
  if (score >= 0.35) return "medium";
  return "low";
}

export function importanceWeight(id: MemoryImportance): number {
  return getImportanceMeta(id).weight;
}

// ── Sources ───────────────────────────────────────────────────────────────────

export type MemorySource = "conversation" | "manual" | "imported" | "agent";

export const MEMORY_SOURCE_LABEL: Record<MemorySource, string> = {
  conversation: "Learned in conversation",
  manual: "Added by you",
  imported: "Imported",
  agent: "Saved by an agent",
};

export function getSourceLabel(source: string): string {
  return MEMORY_SOURCE_LABEL[source as MemorySource] ?? "Unknown source";
}
