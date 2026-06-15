import type { Metadata } from "next";

import { MemoryCenter } from "@/components/memory/MemoryCenter";

export const metadata: Metadata = {
  title: "Memory",
};

/**
 * Memory Center — the first-class memory management experience (Phase 4 · M4).
 * View, search, filter, manage, and explore what GUMMY remembers about you.
 */
export default function MemoriesPage() {
  return <MemoryCenter />;
}
