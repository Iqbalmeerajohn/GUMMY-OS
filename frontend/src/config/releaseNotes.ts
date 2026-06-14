/**
 * Release notes — the "What's New in GUMMY" feed.
 *
 * Data-driven and configurable. Newest first. The What's New surface and any
 * "new since your last visit" badge read from this list — never hardcoded.
 */

import type { ReleaseNote } from "./types";

export const RELEASE_NOTES: ReleaseNote[] = [
  {
    version: "0.4.0",
    date: "2026-06-15",
    title: "GUMMY Web MVP — foundations",
    items: [
      {
        kind: "feature",
        text: "New web experience: a Personal AI Operating System, not a chat window.",
      },
      {
        kind: "feature",
        text: "Memory System, Goals & Tasks, Search, and Multi-Agent Activity are live.",
      },
      {
        kind: "improvement",
        text: "Dark-first, gummy-green design system across the product.",
      },
      {
        kind: "update",
        text: "Career, Learning, Research and more agents are on the roadmap.",
      },
    ],
  },
];
