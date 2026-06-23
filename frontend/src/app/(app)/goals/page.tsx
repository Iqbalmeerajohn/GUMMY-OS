import type { Metadata } from "next";

import { GoalsCenter } from "@/components/goals/GoalsCenter";

export const metadata: Metadata = {
  title: "Goals",
};

/**
 * Goals — the first-class goal management experience (Phase 5 · M5). Create,
 * edit, complete, archive, and track progress (with milestones) for everything
 * the user is working toward.
 */
export default function GoalsPage() {
  return <GoalsCenter />;
}
