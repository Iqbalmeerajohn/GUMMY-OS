"use client";

import Link from "next/link";

import { LivingOrb } from "@/components/brand/LivingOrb";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { buttonVariants } from "@/components/ui/button";
import { useUpdates } from "./UpdatesProvider";
import { cn } from "@/lib/utils";

/** "New in GUMMY" announcement — shown automatically within the 24h window. */
export function WhatsNewModal() {
  const { announcement, open, closeModal } = useUpdates();
  if (!announcement) return null;

  return (
    <Dialog
      open={open}
      onOpenChange={(next: boolean) => {
        if (!next) closeModal();
      }}
    >
      <DialogContent className="sm:max-w-md">
        <div className="flex flex-col items-center gap-4 text-center">
          <LivingOrb size={72} state="update" />
          <span className="text-primary/85 text-xs font-medium tracking-[0.22em] uppercase">
            New in GUMMY
          </span>
          <DialogHeader className="gap-2">
            <DialogTitle className="font-heading text-center text-xl">
              {announcement.title}
            </DialogTitle>
            <DialogDescription className="text-center text-balance">
              {announcement.description}
            </DialogDescription>
          </DialogHeader>
        </div>
        <DialogFooter className="sm:justify-center">
          {announcement.route ? (
            <Link
              href={announcement.route}
              onClick={closeModal}
              className={cn(buttonVariants({ size: "lg" }), "gummy-glow h-10")}
            >
              Explore
            </Link>
          ) : (
            <button
              onClick={closeModal}
              className={cn(buttonVariants({ size: "lg" }), "gummy-glow h-10")}
            >
              Got it
            </button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
