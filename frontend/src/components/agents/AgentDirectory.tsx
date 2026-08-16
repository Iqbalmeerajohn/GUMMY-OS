"use client";

import { StatusBadge } from "@/components/feature/StatusBadge";
import { agentStatusLabel, getAgents } from "@/config/registry";
import { getIcon } from "@/lib/icons";

/**
 * The agent roster, as a panel. Each card states what the agent handles and
 * whether it is live on the chat path or still planned — so the directory
 * never implies capability the backend does not have.
 */
export function AgentDirectory() {
  const agents = getAgents();
  return (
    <div className="h-full min-h-0 space-y-3 overflow-y-auto p-4">
      <p className="text-muted-foreground text-xs text-balance">
        GUMMY routes each message to the agent that fits it. You can also pin
        one from the composer.
      </p>
      {agents.map((a) => {
        const Icon = getIcon(a.icon);
        return (
          <div key={a.id} className="glass elevation-2 rounded-2xl p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2.5">
                <span className="bg-accent text-primary grid size-9 shrink-0 place-items-center rounded-xl">
                  <Icon className="size-4.5" />
                </span>
                <span className="font-heading text-base font-semibold">
                  {a.title}
                </span>
              </span>
              <StatusBadge
                status={a.status}
                label={agentStatusLabel(a.status)}
              />
            </div>
            <p className="text-muted-foreground mt-2 text-sm">
              {a.description}
            </p>
            {a.highlights?.length ? (
              <ul className="mt-3 space-y-1.5 border-t border-white/10 pt-3">
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
        );
      })}
    </div>
  );
}
