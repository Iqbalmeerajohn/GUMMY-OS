import { Badge } from "@/components/ui/badge";
import { LivingOrb } from "@/components/brand/LivingOrb";
import { Reveal } from "@/components/motion/Reveal";
import { Stagger, StaggerItem } from "@/components/motion/Stagger";
import { POSITIONING } from "@/config";

/**
 * M0.5 design-foundation splash — a premium first impression that proves the
 * GUMMY visual language (Living Orb, ambient depth, display type, motion). The
 * full Landing / onboarding / Discover experiences are built in M2 on this base.
 */
export default function Home() {
  return (
    <main className="relative flex flex-1 flex-col items-center justify-center px-6 py-24">
      <Reveal className="flex flex-col items-center">
        <LivingOrb size={220} state="idle" className="mb-12" />
      </Reveal>

      <Reveal delay={0.1} className="flex flex-col items-center">
        <Badge
          variant="secondary"
          className="glass mb-6 rounded-full px-3 py-1 text-xs font-medium tracking-wide"
        >
          Personal AI Operating System
        </Badge>

        <h1 className="font-heading bg-gradient-to-b from-white to-white/60 bg-clip-text text-center text-6xl font-semibold tracking-tight text-transparent sm:text-7xl">
          GUMMY
        </h1>
        <p className="text-muted-foreground mt-4 max-w-md text-center text-lg text-balance">
          Memory, goals, and a team of agents — one living operating layer.
        </p>
      </Reveal>

      <Stagger className="mt-12 flex max-w-2xl flex-wrap justify-center gap-2.5">
        {POSITIONING.map((p) => (
          <StaggerItem key={p.label}>
            <span className="glass elevation-2 hover:text-foreground inline-block rounded-full px-4 py-2 text-sm text-balance transition-colors">
              {p.label}
            </span>
          </StaggerItem>
        ))}
      </Stagger>
    </main>
  );
}
