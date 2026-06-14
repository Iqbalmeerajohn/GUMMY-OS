"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

import { ease } from "@/lib/motion";
import { cn } from "@/lib/utils";

/**
 * Fade + rise a block into view. Honors prefers-reduced-motion (renders static).
 */
export function Reveal({
  children,
  className,
  delay = 0,
  once = true,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  once?: boolean;
}) {
  const reduce = useReducedMotion();

  if (reduce) {
    return <div className={className}>{children}</div>;
  }

  return (
    <motion.div
      className={cn(className)}
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once, margin: "-10% 0px" }}
      transition={{ ...ease, delay }}
    >
      {children}
    </motion.div>
  );
}
