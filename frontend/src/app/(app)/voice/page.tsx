import type { Metadata } from "next";

import { RoadmapPage } from "@/components/app/RoadmapPage";

export const metadata: Metadata = {
  title: "Voice",
};

/** Future voice roadmap (no functionality — extension point only). */
export default function VoicePage() {
  return (
    <RoadmapPage
      kicker="Planned"
      title="Voice"
      intro="A natural, spoken way to work with GUMMY — designed, not yet built."
      entries={[
        {
          title: "Voice conversations",
          description: "Talk to GUMMY and hear it respond, hands-free.",
          status: "researching",
        },
        {
          title: "Voice memory",
          description: "Capture and recall memories by speaking.",
        },
        {
          title: "Multilingual voice",
          description: "Speak and be understood across languages.",
        },
        {
          title: "Screen-aware voice",
          description: "Voice that understands what you're looking at.",
        },
        {
          title: "Voice workflow execution",
          description: "Trigger workflows and tasks by voice.",
        },
        {
          title: "Wake-word support",
          description: "Summon GUMMY hands-free with a wake word.",
        },
        {
          title: "Voice + agent collaboration",
          description: "Direct a team of agents out loud.",
        },
      ]}
    />
  );
}
