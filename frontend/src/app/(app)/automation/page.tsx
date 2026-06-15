import type { Metadata } from "next";

import { RoadmapPage } from "@/components/app/RoadmapPage";

export const metadata: Metadata = {
  title: "Automation",
};

/** Future automation roadmap (no functionality — extension point only). */
export default function AutomationPage() {
  return (
    <RoadmapPage
      kicker="Planned"
      title="Automation"
      intro="Tell GUMMY what you want done, and let it coordinate the work — with your approval."
      entries={[
        {
          title: "Workflow Learning",
          description:
            "GUMMY learns your recurring workflows by watching how you work.",
          status: "researching",
        },
        {
          title: "N8N Integration",
          description: "Bring your own workflows and run them through GUMMY.",
        },
        {
          title: "Browser Automation",
          description: "Safe, sandboxed web actions on your behalf.",
          status: "researching",
        },
        {
          title: "Tool Orchestration",
          description: "Connect calendars, email, documents, and services.",
        },
        {
          title: "Agent Orchestration",
          description: "Coordinate multiple agents toward one outcome.",
        },
        {
          title: "Business Automation",
          description: "Automate operations and reporting.",
        },
        {
          title: "Content Automation",
          description: "Produce and publish content across platforms.",
        },
        {
          title: "Personal Automation",
          description: "Automate the small, repetitive parts of your day.",
        },
      ]}
    />
  );
}
