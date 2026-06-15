import type { Metadata } from "next";

import { StatusBadge } from "@/components/feature/StatusBadge";
import { Reveal } from "@/components/motion/Reveal";
import { Stagger, StaggerItem } from "@/components/motion/Stagger";
import { agentStatusLabel, getAgents } from "@/config/registry";
import { getIcon } from "@/lib/icons";

export const metadata: Metadata = {
  title: "Agents",
};

/** Agent Directory — every agent, from the registry. No functionality yet. */
export default function AgentsPage() {
  const agents = getAgents();
  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <Reveal>
        <p className="text-primary/85 text-xs font-medium tracking-[0.28em] uppercase">
          The team
        </p>
        <h1 className="font-heading mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          Agent Directory
        </h1>
        <p className="text-muted-foreground mt-2 max-w-2xl">
          Specialized agents that will work together inside GUMMY. Each handles
          a different kind of work.
        </p>
      </Reveal>

      <Stagger className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map((a) => {
          const Icon = getIcon(a.icon);
          return (
            <StaggerItem key={a.id}>
              <div className="glass elevation-2 flex h-full flex-col rounded-2xl p-5">
                <div className="flex items-center justify-between">
                  <span className="bg-accent text-primary grid size-10 place-items-center rounded-xl">
                    <Icon className="size-5" />
                  </span>
                  <StatusBadge
                    status={a.status}
                    label={agentStatusLabel(a.status)}
                  />
                </div>
                <h2 className="font-heading mt-4 text-lg font-semibold">
                  {a.title}
                </h2>
                <p className="text-muted-foreground mt-1 text-sm">
                  {a.description}
                </p>
                {a.highlights?.length ? (
                  <ul className="mt-4 space-y-1.5 border-t border-white/10 pt-4">
                    {a.highlights.map((h) => (
                      <li
                        key={h}
                        className="text-muted-foreground flex items-center gap-2 text-xs"
                      >
                        <span className="bg-primary/70 size-1.5 rounded-full" />
                        {h}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            </StaggerItem>
          );
        })}
      </Stagger>
    </div>
  );
}
