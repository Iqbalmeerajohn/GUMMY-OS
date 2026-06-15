"use client";

import { motion, useReducedMotion } from "framer-motion";

import { LivingOrb } from "@/components/brand/LivingOrb";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useUpdates } from "@/components/updates/UpdatesProvider";

/**
 * Orb notification — appears only when an unseen update exists. Softly pulses
 * and opens the "New in GUMMY" modal on click (the UPDATE_AVAILABLE state).
 */
export function OrbNotification() {
  const reduce = useReducedMotion();
  const { updateAvailable, openModal } = useUpdates();

  if (!updateAvailable) return null;

  return (
    <Tooltip>
      <TooltipTrigger
        onClick={openModal}
        aria-label="GUMMY learned something new"
        className="relative grid size-9 place-items-center rounded-full"
      >
        <motion.span
          className="absolute inset-1"
          animate={reduce ? undefined : { scale: [1, 1.15, 1] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
        >
          <LivingOrb size={28} state="update" />
        </motion.span>
      </TooltipTrigger>
      <TooltipContent>GUMMY learned something new.</TooltipContent>
    </Tooltip>
  );
}
