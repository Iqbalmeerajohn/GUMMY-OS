import type { Metadata } from "next";

import { StatusBadge } from "@/components/feature/StatusBadge";
import { Reveal } from "@/components/motion/Reveal";
import { Stagger, StaggerItem } from "@/components/motion/Stagger";
import { getByStatus, getReleased } from "@/config/registry";
import { getIcon } from "@/lib/icons";

export const metadata: Metadata = {
  title: "Updates",
};

function formatDate(iso?: string) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

/** Product updates / changelog — generated entirely from the Feature Registry. */
export default function UpdatesPage() {
  const released = getReleased();
  const inProgress = getByStatus("in-development");

  return (
    <div className="mx-auto max-w-2xl space-y-10">
      <Reveal>
        <p className="text-primary/85 text-xs font-medium tracking-[0.28em] uppercase">
          Changelog
        </p>
        <h1 className="font-heading mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
          Product Updates
        </h1>
        <p className="text-muted-foreground mt-2">
          Everything that has shipped, newest first.
        </p>
      </Reveal>

      {/* Timeline */}
      <Stagger className="relative space-y-5 border-l border-white/10 pl-6">
        {released.map((f) => {
          const Icon = getIcon(f.icon);
          return (
            <StaggerItem key={f.id}>
              <div className="relative">
                <span className="bg-primary text-primary-foreground absolute -left-[37px] grid size-6 place-items-center rounded-full">
                  <Icon className="size-3.5" />
                </span>
                <div className="glass elevation-2 rounded-2xl p-5">
                  <div className="flex items-center justify-between gap-2">
                    <h2 className="font-heading text-lg font-semibold">
                      {f.title}
                    </h2>
                    <StatusBadge status={f.status} />
                  </div>
                  <p className="text-muted-foreground mt-1 text-sm">
                    {f.description}
                  </p>
                  <p className="text-muted-foreground mt-2 text-xs">
                    {formatDate(f.released_at)}
                  </p>
                </div>
              </div>
            </StaggerItem>
          );
        })}
      </Stagger>

      {inProgress.length ? (
        <section className="space-y-4">
          <h2 className="text-muted-foreground text-xs font-medium tracking-[0.15em] uppercase">
            In progress
          </h2>
          <div className="space-y-2.5">
            {inProgress.map((f) => (
              <div
                key={f.id}
                className="border-border/50 flex items-center justify-between gap-2 rounded-xl border p-3.5"
              >
                <span className="text-sm font-medium">{f.title}</span>
                <StatusBadge status={f.status} />
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
