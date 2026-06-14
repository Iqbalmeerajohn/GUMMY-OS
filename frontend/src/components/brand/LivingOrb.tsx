"use client";

import dynamic from "next/dynamic";
import { useReducedMotion } from "framer-motion";

import { cn } from "@/lib/utils";
import type { OrbState } from "./orb-state";

const OrbScene = dynamic(() => import("./OrbScene"), { ssr: false });

/** Static, dependency-free orb — favicon/loading/reduced-motion fallback. */
function OrbFallback({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "size-full rounded-full",
        "bg-[radial-gradient(circle_at_35%_30%,#9bffd6,40%,#16c98a_70%,#0c7a52)]",
        className,
      )}
      style={{ boxShadow: "0 0 60px rgba(63,224,160,0.45)" }}
    />
  );
}

/**
 * The Living Orb — GUMMY's animated brand presence.
 *
 * Renders a single R3F canvas with a soft CSS glow halo behind it. Falls back to
 * a static gradient orb for prefers-reduced-motion. Lazy (ssr:false) so first
 * paint stays fast and three.js never ships to the server.
 */
export function LivingOrb({
  state = "idle",
  size = 200,
  className,
}: {
  state?: OrbState;
  size?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();

  return (
    <div
      className={cn("relative", className)}
      style={{ width: size, height: size }}
    >
      {/* Ambient glow halo (cheap, no postprocessing). */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 rounded-full blur-2xl"
        style={{
          background:
            "radial-gradient(circle, rgba(63,224,160,0.45) 0%, rgba(63,224,160,0.12) 45%, transparent 70%)",
          transform: "scale(1.5)",
        }}
      />
      {reduce ? <OrbFallback /> : <OrbScene state={state} />}
    </div>
  );
}
