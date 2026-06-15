import { LivingOrb } from "@/components/brand/LivingOrb";
import { StatusBadge } from "@/components/feature/StatusBadge";
import { Reveal } from "@/components/motion/Reveal";
import { Stagger, StaggerItem } from "@/components/motion/Stagger";
import type { FeatureStatus } from "@/config/registry";

export interface RoadmapEntry {
  title: string;
  description: string;
  status?: FeatureStatus;
}

/** Shared premium layout for future-capability roadmap pages (Voice, Automation). */
export function RoadmapPage({
  kicker,
  title,
  intro,
  entries,
}: {
  kicker: string;
  title: string;
  intro: string;
  entries: RoadmapEntry[];
}) {
  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <Reveal className="flex flex-col items-center gap-6 py-4 text-center">
        <LivingOrb size={120} state="idle" />
        <div>
          <p className="text-primary/85 text-xs font-medium tracking-[0.28em] uppercase">
            {kicker}
          </p>
          <h1 className="font-heading mt-2 text-4xl font-semibold tracking-tight sm:text-5xl">
            {title}
          </h1>
          <p className="text-muted-foreground mx-auto mt-3 max-w-xl text-balance">
            {intro}
          </p>
        </div>
      </Reveal>

      <Stagger className="grid gap-3 sm:grid-cols-2">
        {entries.map((e) => (
          <StaggerItem key={e.title}>
            <div className="glass elevation-2 h-full rounded-2xl p-5">
              <div className="flex items-center justify-between gap-2">
                <h2 className="font-heading text-base font-semibold">
                  {e.title}
                </h2>
                <StatusBadge status={e.status ?? "planned"} />
              </div>
              <p className="text-muted-foreground mt-1.5 text-sm">
                {e.description}
              </p>
            </div>
          </StaggerItem>
        ))}
      </Stagger>
    </div>
  );
}
