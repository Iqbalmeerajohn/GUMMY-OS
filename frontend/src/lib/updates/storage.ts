"use client";

/** First-seen tracking for product-update announcements (24h visibility). */

export const UPDATE_WINDOW_MS = 24 * 60 * 60 * 1000;

function key(id: string): string {
  return `gummy.update.firstSeen.${id}`;
}

export function getFirstSeen(id: string): number | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(key(id));
  return raw ? Number(raw) : null;
}

export function setFirstSeen(id: string, ts: number): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(key(id), String(ts));
}

/** Within the 24h window since first seen (announcement still visible). */
export function isWithinWindow(firstSeen: number): boolean {
  return Date.now() - firstSeen < UPDATE_WINDOW_MS;
}
