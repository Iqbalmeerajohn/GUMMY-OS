import type { Metadata } from "next";

import { Reveal } from "@/components/motion/Reveal";
import {
  ActivityWidget,
  GoalsWidget,
  GreetingHeader,
  QuickStartWidget,
  RecentMemoriesWidget,
  RecommendedActionsWidget,
} from "@/components/dashboard/widgets";

export const metadata: Metadata = {
  title: "Dashboard",
};

/**
 * Welcome Dashboard — the OS home. Greets the user, surfaces recent memories,
 * goals, and activity, and offers recommended actions + quick starts. Never a
 * blank chat.
 */
export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <Reveal>
        <GreetingHeader />
      </Reveal>

      <Reveal delay={0.05}>
        <RecommendedActionsWidget />
      </Reveal>

      <div className="grid gap-5 lg:grid-cols-3">
        <Reveal delay={0.1} className="lg:col-span-1">
          <RecentMemoriesWidget />
        </Reveal>
        <Reveal delay={0.15} className="lg:col-span-1">
          <GoalsWidget />
        </Reveal>
        <Reveal delay={0.2} className="lg:col-span-1">
          <ActivityWidget />
        </Reveal>
      </div>

      <Reveal delay={0.1}>
        <QuickStartWidget />
      </Reveal>
    </div>
  );
}
