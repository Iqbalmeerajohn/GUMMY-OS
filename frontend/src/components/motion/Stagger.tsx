"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

import { staggerContainer, staggerItem } from "@/lib/motion";
import { cn } from "@/lib/utils";

/** Container that staggers its <StaggerItem> children into view. */
export function Stagger({
  children,
  className,
  once = true,
}: {
  children: ReactNode;
  className?: string;
  once?: boolean;
}) {
  const reduce = useReducedMotion();

  if (reduce) {
    return <div className={className}>{children}</div>;
  }

  return (
    <motion.div
      className={cn(className)}
      variants={staggerContainer}
      initial="hidden"
      whileInView="visible"
      viewport={{ once, margin: "-10% 0px" }}
    >
      {children}
    </motion.div>
  );
}

/** A single staggered child. Use inside <Stagger>. */
export function StaggerItem({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const reduce = useReducedMotion();

  if (reduce) {
    return <div className={className}>{children}</div>;
  }

  return (
    <motion.div className={cn(className)} variants={staggerItem}>
      {children}
    </motion.div>
  );
}
