import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";

import { LivingOrb } from "@/components/brand/LivingOrb";
import { StatusBadge } from "@/components/feature/StatusBadge";
import { Reveal } from "@/components/motion/Reveal";
import { Stagger, StaggerItem } from "@/components/motion/Stagger";
import {
  EVOLUTION_STAGES,
  LONG_TERM_VISION,
  VISION_PILLARS,
  getByStatus,
  getReleased,
} from "@/config/registry";
import { getIcon } from "@/lib/icons";

export const metadata: Metadata = {
  title: "Future Vision",
};

const ROADMAP = [
  ...getByStatus("in-development"),
  ...getByStatus("planned"),
  ...getByStatus("researching"),
];

const CROSS_LINKS = [
  { href: "/agents", label: "Agent Directory" },
  { href: "/voice", label: "Voice" },
  { href: "/automation", label: "Automation" },
  { href: "/about-gummy", label: "About GUMMY" },
] as const;

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
      {children}
    </h2>
  );
}

/** The living roadmap inside GUMMY — generated from the Feature Registry. */
export default function FuturePage() {
  const released = getReleased();

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-20 py-4">
      <Reveal className="flex flex-col items-center gap-6 text-center">
        <LivingOrb size={140} state="idle" />
        <div>
          <p className="text-primary/85 text-xs font-medium tracking-[0.28em] uppercase">
            Living roadmap
          </p>
          <h1 className="font-heading mt-2 text-4xl font-semibold tracking-tight sm:text-5xl">
            The Future of GUMMY
          </h1>
        </div>
      </Reveal>

      {/* Today */}
      <section className="space-y-6">
        <Reveal>
          <SectionHeading>Where GUMMY Is Today</SectionHeading>
        </Reveal>
        <Stagger className="grid gap-2.5 sm:grid-cols-2">
          {released.map((m) => (
            <StaggerItem key={m.id}>
              <div className="glass flex items-center gap-3 rounded-xl px-4 py-3">
                <span className="bg-primary text-primary-foreground grid size-6 shrink-0 place-items-center rounded-full">
                  <Check className="size-3.5" />
                </span>
                <span className="text-sm font-medium">{m.title}</span>
              </div>
            </StaggerItem>
          ))}
        </Stagger>
      </section>

      {/* Becoming */}
      <section className="space-y-6">
        <Reveal>
          <SectionHeading>What GUMMY Is Becoming</SectionHeading>
          <p className="text-muted-foreground mt-2 max-w-2xl">
            Four things working together as one system.
          </p>
        </Reveal>
        <Stagger className="grid gap-3 sm:grid-cols-2">
          {VISION_PILLARS.map((p) => (
            <StaggerItem key={p.title}>
              <div className="glass elevation-2 h-full rounded-2xl p-5">
                <h3 className="font-heading text-lg font-semibold">
                  {p.title}
                </h3>
                <p className="text-muted-foreground mt-1 text-sm">
                  {p.description}
                </p>
              </div>
            </StaggerItem>
          ))}
        </Stagger>
      </section>

      {/* Planned evolution */}
      <section className="space-y-6">
        <Reveal>
          <p className="text-primary/85 text-xs font-medium tracking-[0.2em] uppercase">
            Planned Evolution
          </p>
          <SectionHeading>Future Capabilities</SectionHeading>
        </Reveal>
        <Stagger className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {ROADMAP.map((c) => {
            const Icon = getIcon(c.icon);
            return (
              <StaggerItem key={c.id}>
                <div className="group hover:border-primary/40 relative h-full overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] p-5 transition-colors">
                  <div className="from-primary/10 absolute inset-0 bg-gradient-to-br to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
                  <div className="relative flex items-center justify-between gap-2">
                    <Icon className="text-primary size-5" />
                    <StatusBadge status={c.status} />
                  </div>
                  <h3 className="relative mt-3 text-sm font-semibold">
                    {c.title}
                  </h3>
                  <p className="text-muted-foreground relative mt-1 text-xs">
                    {c.description}
                  </p>
                </div>
              </StaggerItem>
            );
          })}
        </Stagger>
      </section>

      {/* Long-term vision */}
      <section>
        <Reveal className="glass elevation-2 rounded-3xl p-8 text-center sm:p-12">
          <SectionHeading>The Long-Term Vision</SectionHeading>
          <p className="text-muted-foreground mx-auto mt-4 max-w-2xl text-lg text-balance">
            {LONG_TERM_VISION}
          </p>
        </Reveal>
      </section>

      {/* Your future */}
      <section className="space-y-6">
        <Reveal>
          <SectionHeading>Your Future With GUMMY</SectionHeading>
        </Reveal>
        <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
          {EVOLUTION_STAGES.map((stage, i) => (
            <div key={stage.when} className="flex flex-1 items-center gap-3">
              <Reveal delay={i * 0.1} className="flex-1">
                <div className="glass elevation-2 rounded-2xl p-6 text-center">
                  <p className="text-muted-foreground text-xs tracking-[0.2em] uppercase">
                    {stage.when}
                  </p>
                  <p className="font-heading mt-2 text-xl font-semibold">
                    {stage.what}
                  </p>
                </div>
              </Reveal>
              {i < EVOLUTION_STAGES.length - 1 ? (
                <ArrowRight className="text-primary/60 hidden size-5 shrink-0 sm:block" />
              ) : null}
            </div>
          ))}
        </div>
      </section>

      {/* Cross-links */}
      <section className="flex flex-wrap justify-center gap-2.5">
        {CROSS_LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className="glass hover:border-primary/40 inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm transition-colors"
          >
            {l.label}
            <ArrowRight className="size-3.5" />
          </Link>
        ))}
      </section>
    </div>
  );
}
