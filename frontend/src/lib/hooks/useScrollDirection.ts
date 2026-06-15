"use client";

import { useEffect, useState } from "react";

/**
 * iPhone-style nav visibility: hide on scroll down, reveal on scroll up.
 * Tracks window scroll; always visible near the top.
 */
export function useHideOnScroll(threshold = 8): boolean {
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    let last = window.scrollY;
    let ticking = false;

    const update = () => {
      const y = window.scrollY;
      const delta = y - last;
      if (Math.abs(delta) > threshold) {
        setHidden(delta > 0 && y > 64);
        last = y;
      }
      ticking = false;
    };

    const onScroll = () => {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(update);
      }
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [threshold]);

  return hidden;
}
