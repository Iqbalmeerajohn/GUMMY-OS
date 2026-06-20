import type { Metadata } from "next";

import { TrackOnce } from "@/components/analytics/TrackOnce";
import { AnalyticsEvent } from "@/lib/analytics";
import { Reveal } from "@/components/motion/Reveal";
import {
  ActiveAgents,
  CapabilityMap,
  TodaysFocus,
  WhatsNewWidget,
} from "@/components/dashboard/command-center";
import {
  ActivityWidget,
  GoalsWidget,
  GreetingHeader,
  QuickStartWidget,
  RecentMemoriesWidget,
  RecommendedActionsWidget,
  SystemHealthWidget,
} from "@/components/dashboard/widgets";

export const metadata: Metadata = {
  title: "Dashboard",
};

/**
 * Command Center — the OS home. Today's focus, what's new, active agents, and
 * the capability map up top; live memories/goals/activity below. Never a blank
 * chat. Agent + capability data is registry-driven (single source of truth).
 */
export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <TrackOnce event={AnalyticsEvent.DashboardViewed} />
      <Reveal>
        <GreetingHeader />
      </Reveal>

      <Reveal delay={0.04}>
        <TodaysFocus />
      </Reveal>

      <Reveal delay={0.06}>
        <SystemHealthWidget />
      </Reveal>

      <div className="grid gap-6 lg:grid-cols-2">
        <Reveal delay={0.08}>
          <WhatsNewWidget />
        </Reveal>
        <Reveal delay={0.12}>
          <RecommendedActionsWidget />
        </Reveal>
      </div>

      <Reveal delay={0.08}>
        <ActiveAgents />
      </Reveal>

      <Reveal delay={0.08}>
        <CapabilityMap />
      </Reveal>

      <div className="grid gap-5 lg:grid-cols-3">
        <Reveal delay={0.1}>
          <RecentMemoriesWidget />
        </Reveal>
        <Reveal delay={0.14}>
          <GoalsWidget />
        </Reveal>
        <Reveal delay={0.18}>
          <ActivityWidget />
        </Reveal>
      </div>

      <Reveal delay={0.1}>
        <QuickStartWidget />
      </Reveal>
    </div>
  );
}
