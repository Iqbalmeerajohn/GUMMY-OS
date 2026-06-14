/**
 * Config-driven registry types.
 *
 * GUMMY's UI must never hardcode features. Capabilities, release notes, the
 * Discover content, and positioning are all *data* — adding a future feature or
 * agent is a config edit here, not a code change. Onboarding cards, the Discover
 * page, the capability grid, and "What's New" all render from these structures.
 */

export type CapabilityStatus = "active" | "coming-soon" | "future";

export type CapabilityCategory = "core" | "agent" | "automation" | "vision";

export interface Capability {
  /** Stable id (kebab-case) — also the analytics/event key. */
  id: string;
  name: string;
  /** One-line, user-facing description (used on onboarding cards). */
  description: string;
  status: CapabilityStatus;
  category: CapabilityCategory;
  /** lucide-react icon name (resolved at render time, never hardcoded in JSX). */
  icon: string;
  /** Route when the capability is active; omitted for coming-soon/future. */
  href?: string;
  /** Manual ordering within a group (lower = first). */
  order: number;
}

export type ReleaseNoteKind = "feature" | "improvement" | "agent" | "update";

export interface ReleaseNoteItem {
  kind: ReleaseNoteKind;
  text: string;
}

export interface ReleaseNote {
  version: string;
  /** ISO date (YYYY-MM-DD). */
  date: string;
  title: string;
  items: ReleaseNoteItem[];
}

export interface DiscoverSection {
  id: string;
  title: string;
  /** Markdown-friendly body paragraphs. */
  body: string[];
  /** Optional: render the capabilities of these statuses inline. */
  showCapabilities?: CapabilityStatus[];
}

export interface PositioningStatement {
  label: string;
  description: string;
}

export interface ComparisonRow {
  dimension: string;
  /** Neutral, factual description of typical AI tools — never derogatory. */
  traditional: string;
  /** What GUMMY adds. */
  gummy: string;
}
