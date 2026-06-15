"use client";

import { motion, useReducedMotion } from "framer-motion";
import { Check } from "lucide-react";

import { HeroOrb } from "@/components/brand/HeroOrb";
import { LivingOrb } from "@/components/brand/LivingOrb";
import type { OnboardingStep, OnboardingVisual } from "@/config/onboarding";
import { cn } from "@/lib/utils";

interface VisualProps {
  step: OnboardingStep;
}

/** Visuals that render the step's items themselves (so the shell skips pills). */
export function visualShowsItems(visual: OnboardingVisual): boolean {
  return (
    visual === "ecosystem" ||
    visual === "roadmap-current" ||
    visual === "roadmap-future"
  );
}

/** Screen 1 — the orb awakens with a connecting aura. */
function AwakenVisual() {
  return (
    <div className="flex justify-center">
      <HeroOrb />
    </div>
  );
}

/** Screen 2 — a timeline resolving into connected memory nodes. */
function MemoryVisual() {
  const reduce = useReducedMotion();
  const nodes = [0, 1, 2, 3, 4];
  return (
    <div className="relative mx-auto flex h-40 w-full max-w-md items-center justify-between px-4">
      <div className="bg-border absolute inset-x-4 top-1/2 h-px -translate-y-1/2" />
      <div
        className="from-primary/0 via-primary to-primary/0 absolute inset-x-4 top-1/2 h-px -translate-y-1/2 bg-gradient-to-r"
        style={{ opacity: 0.6 }}
      />
      {nodes.map((i) => (
        <motion.span
          key={i}
          className="bg-primary relative size-3 rounded-full"
          style={{ boxShadow: "0 0 14px rgba(63,224,160,0.7)" }}
          initial={reduce ? false : { scale: 0, opacity: 0 }}
          whileInView={reduce ? undefined : { scale: 1, opacity: 1 }}
          viewport={{ once: true }}
          transition={{ delay: i * 0.12, type: "spring", stiffness: 300 }}
        />
      ))}
    </div>
  );
}

/** Screen 3 — agent dots orbiting the Living Orb. */
function AgentsVisual() {
  const reduce = useReducedMotion();
  const dots = [0, 60, 120, 180, 240, 300];
  const radius = 110;
  return (
    <div className="relative mx-auto flex size-64 items-center justify-center">
      <div className="absolute inset-[22%]">
        <LivingOrb state="thinking" />
      </div>
      <motion.div
        className="absolute inset-0"
        animate={reduce ? undefined : { rotate: 360 }}
        transition={{ duration: 38, repeat: Infinity, ease: "linear" }}
      >
        {dots.map((deg) => (
          <span
            key={deg}
            className="bg-primary/90 absolute top-1/2 left-1/2 size-2.5 rounded-full"
            style={{
              boxShadow: "0 0 12px rgba(63,224,160,0.7)",
              transform: `rotate(${deg}deg) translateY(-${radius}px)`,
            }}
          />
        ))}
      </motion.div>
    </div>
  );
}

/** Screen 4 — goal → tasks → progress → completion. */
function GoalsVisual() {
  const reduce = useReducedMotion();
  return (
    <div className="mx-auto flex h-40 w-full max-w-md flex-col justify-center gap-4">
      <div className="flex items-center gap-3">
        <span className="border-primary/60 text-primary grid size-9 place-items-center rounded-xl border text-xs font-medium">
          Goal
        </span>
        <div className="flex flex-1 items-center gap-1.5">
          {[0, 1, 2].map((i) => (
            <span key={i} className="bg-muted h-2 flex-1 rounded-full">
              <motion.span
                className="bg-primary block h-full rounded-full"
                initial={reduce ? false : { width: 0 }}
                whileInView={{ width: "100%" }}
                viewport={{ once: true }}
                transition={{ delay: 0.3 + i * 0.25, duration: 0.5 }}
              />
            </span>
          ))}
        </div>
        <motion.span
          className="bg-primary text-primary-foreground grid size-9 place-items-center rounded-xl"
          initial={reduce ? false : { scale: 0 }}
          whileInView={{ scale: 1 }}
          viewport={{ once: true }}
          transition={{ delay: 1.2, type: "spring", stiffness: 300 }}
        >
          <Check className="size-5" />
        </motion.span>
      </div>
      <p className="text-muted-foreground text-center text-xs">
        Goal → Tasks → Progress → Completion
      </p>
    </div>
  );
}

/** Screen 5 — connected ecosystem graph (labels from the step's items). */
function EcosystemVisual({ step }: VisualProps) {
  const items = step.items ?? [];
  const radius = 96;
  return (
    <div className="relative mx-auto flex size-64 items-center justify-center">
      <svg className="absolute inset-0 size-full" aria-hidden>
        {items.map((_, i) => {
          const angle = (i / items.length) * Math.PI * 2 - Math.PI / 2;
          const x = 128 + Math.cos(angle) * radius;
          const y = 128 + Math.sin(angle) * radius;
          return (
            <line
              key={i}
              x1="128"
              y1="128"
              x2={x}
              y2={y}
              stroke="rgba(63,224,160,0.25)"
              strokeWidth="1"
            />
          );
        })}
      </svg>
      <span className="bg-primary gummy-glow size-10 rounded-full" />
      {items.map((item, i) => {
        const angle = (i / items.length) * Math.PI * 2 - Math.PI / 2;
        const x = Math.cos(angle) * radius;
        const y = Math.sin(angle) * radius;
        return (
          <span
            key={item.title}
            className="glass absolute rounded-full px-2.5 py-1 text-[11px] font-medium whitespace-nowrap"
            style={{ transform: `translate(${x}px, ${y}px)` }}
          >
            {item.title}
          </span>
        );
      })}
    </div>
  );
}

/** Screen 6 — completed milestones on a track. */
function RoadmapCurrentVisual({ step }: VisualProps) {
  const items = step.items ?? [];
  return (
    <div className="mx-auto grid w-full max-w-lg grid-cols-1 gap-2.5 sm:grid-cols-2">
      {items.map((item, i) => (
        <motion.div
          key={item.title}
          className="glass flex items-center gap-3 rounded-xl px-4 py-3"
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: i * 0.06 }}
        >
          <span className="bg-primary text-primary-foreground grid size-6 shrink-0 place-items-center rounded-full">
            <Check className="size-3.5" />
          </span>
          <span className="text-sm font-medium">{item.title}</span>
        </motion.div>
      ))}
    </div>
  );
}

/** Screen 7 — upcoming capabilities as a futuristic roadmap. */
function RoadmapFutureVisual({ step }: VisualProps) {
  const items = step.items ?? [];
  return (
    <div className="mx-auto grid w-full max-w-2xl grid-cols-1 gap-2.5 sm:grid-cols-2">
      {items.map((item, i) => (
        <motion.div
          key={item.title}
          className="group relative overflow-hidden rounded-xl border border-white/10 bg-white/[0.03] p-4 text-left"
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: i * 0.05 }}
        >
          <div className="from-primary/10 absolute inset-0 bg-gradient-to-br to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
          <div className="relative flex items-center justify-between gap-2">
            <span className="text-sm font-semibold">{item.title}</span>
            <span className="text-primary/80 border-primary/30 rounded-full border px-2 py-0.5 text-[10px] tracking-wide uppercase">
              Soon
            </span>
          </div>
          {item.desc ? (
            <p className="text-muted-foreground relative mt-1.5 text-xs">
              {item.desc}
            </p>
          ) : null}
        </motion.div>
      ))}
    </div>
  );
}

const VISUALS: Record<
  OnboardingVisual,
  (props: VisualProps) => React.ReactNode
> = {
  awaken: AwakenVisual,
  memory: MemoryVisual,
  agents: AgentsVisual,
  goals: GoalsVisual,
  ecosystem: EcosystemVisual,
  "roadmap-current": RoadmapCurrentVisual,
  "roadmap-future": RoadmapFutureVisual,
};

export function OnboardingVisualView({ step }: VisualProps) {
  const Visual = VISUALS[step.visual];
  return (
    <div className={cn("w-full")}>
      <Visual step={step} />
    </div>
  );
}
