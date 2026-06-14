/**
 * Central motion vocabulary for GUMMY — the "gummy feel".
 *
 * One source of truth for easing, durations, and reusable variants so motion is
 * consistent and communicates state (never decorates emptily). Components import
 * these instead of hardcoding transitions.
 */

import type { Transition, Variants } from "framer-motion";

/** Springy, slightly bouncy easing — the signature gummy motion. */
export const gummySpring: Transition = {
  type: "spring",
  stiffness: 320,
  damping: 28,
  mass: 0.9,
};

/** Smooth eased transition for opacity/position fades. */
export const ease: Transition = {
  duration: 0.5,
  ease: [0.22, 1, 0.36, 1], // easeOutExpo-ish
};

/** Fade + rise in. Pair with `whileInView` or `animate`. */
export const reveal: Variants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: ease },
};

/** Parent that staggers its children's reveal. */
export const staggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.07, delayChildren: 0.05 },
  },
};

/** Child item for use inside `staggerContainer`. */
export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: gummySpring },
};

/** Subtle hover/press micro-interaction for interactive surfaces. */
export const interactive = {
  whileHover: { y: -2, scale: 1.01 },
  whileTap: { scale: 0.985 },
  transition: gummySpring,
} as const;
