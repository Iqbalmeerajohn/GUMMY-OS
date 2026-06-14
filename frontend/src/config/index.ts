/**
 * Config registry barrel + typed accessors.
 *
 * Import from `@/config` everywhere. These helpers are the only way the UI
 * should read capabilities, so feature gating stays data-driven.
 */

import { CAPABILITIES } from "./capabilities";
import { DISCOVER_SECTIONS } from "./discover";
import { COMPARISON, COMPARISON_TOOLS, POSITIONING } from "./positioning";
import { RELEASE_NOTES } from "./releaseNotes";
import type { Capability, CapabilityCategory, CapabilityStatus } from "./types";

export * from "./types";
export {
  CAPABILITIES,
  DISCOVER_SECTIONS,
  COMPARISON,
  COMPARISON_TOOLS,
  POSITIONING,
  RELEASE_NOTES,
};

const byOrder = (a: Capability, b: Capability) => a.order - b.order;

export function getCapabilities(): Capability[] {
  return [...CAPABILITIES].sort(byOrder);
}

export function getCapabilitiesByStatus(
  ...statuses: CapabilityStatus[]
): Capability[] {
  const set = new Set(statuses);
  return getCapabilities().filter((c) => set.has(c.status));
}

export function getCapabilitiesByCategory(
  category: CapabilityCategory,
): Capability[] {
  return getCapabilities().filter((c) => c.category === category);
}

export function getCapability(id: string): Capability | undefined {
  return CAPABILITIES.find((c) => c.id === id);
}

export function isActive(id: string): boolean {
  return getCapability(id)?.status === "active";
}

/** The most recent release note (drives a "What's New" badge). */
export function getLatestRelease() {
  return RELEASE_NOTES[0];
}
