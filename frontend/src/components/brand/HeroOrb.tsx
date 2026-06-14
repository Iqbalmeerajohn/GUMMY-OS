"use client";

import { motion, useReducedMotion } from "framer-motion";

import { LivingOrb } from "./LivingOrb";
import { cn } from "@/lib/utils";

/**
 * The hero composition: the Living Orb (single R3F canvas) surrounded by an
 * elegant, minimal aura built from DOM + Framer Motion — agent-activity pulse
 * rings, floating memory nodes, and a goal indicator. No extra 3D. Aura sits
 * inside the wrapper bounds (orb is inset) so nothing overflows on mobile.
 */
export function HeroOrb() {
  const reduce = useReducedMotion();

  return (
    <div className="relative aspect-square w-44 sm:w-56 md:w-64 lg:w-72">
      {/* Agent-activity pulse rings. */}
      {!reduce &&
        [0, 1].map((i) => (
          <motion.span
            key={i}
            aria-hidden
            className="border-primary/30 absolute inset-[8%] rounded-full border"
            initial={{ scale: 0.85, opacity: 0.5 }}
            animate={{ scale: 1.35, opacity: 0 }}
            transition={{
              duration: 3.2,
              repeat: Infinity,
              ease: "easeOut",
              delay: i * 1.6,
            }}
          />
        ))}

      {/* The orb (inset so the aura has room). */}
      <div className="absolute inset-[11%]">
        <LivingOrb state="idle" />
      </div>

      {/* Floating memory nodes. */}
      <AuraNode className="top-[6%] left-[12%]" reduce={reduce} delay={0} />
      <AuraNode className="top-[24%] right-[4%]" reduce={reduce} delay={0.8} />
      <AuraNode
        className="bottom-[12%] left-[6%] hidden sm:block"
        reduce={reduce}
        delay={1.4}
      />

      {/* Goal indicator. */}
      <GoalDot className="right-[10%] bottom-[18%]" reduce={reduce} />
    </div>
  );
}

function AuraNode({
  className,
  reduce,
  delay,
}: {
  className?: string;
  reduce: boolean | null;
  delay: number;
}) {
  const dot = (
    <span
      className="bg-primary/90 block size-2 rounded-full"
      style={{ boxShadow: "0 0 10px rgba(63,224,160,0.7)" }}
    />
  );
  if (reduce) {
    return (
      <span aria-hidden className={cn("absolute", className)}>
        {dot}
      </span>
    );
  }
  return (
    <motion.span
      aria-hidden
      className={cn("absolute", className)}
      animate={{ y: [0, -6, 0], opacity: [0.5, 1, 0.5] }}
      transition={{ duration: 4, repeat: Infinity, ease: "easeInOut", delay }}
    >
      {dot}
    </motion.span>
  );
}

function GoalDot({
  className,
  reduce,
}: {
  className?: string;
  reduce: boolean | null;
}) {
  const ring = (
    <span className="border-primary/70 block size-3 rounded-full border-2" />
  );
  if (reduce) {
    return (
      <span aria-hidden className={cn("absolute", className)}>
        {ring}
      </span>
    );
  }
  return (
    <motion.span
      aria-hidden
      className={cn("absolute", className)}
      animate={{ scale: [1, 1.18, 1], opacity: [0.6, 1, 0.6] }}
      transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
    >
      {ring}
    </motion.span>
  );
}
