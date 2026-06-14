/**
 * Global UI state (Zustand) — ephemeral, client-only.
 *
 * Server data lives in TanStack Query, not here. This store holds things like
 * the command palette and sidebar state. Feature milestones extend it.
 */

import { create } from "zustand";

interface UiState {
  commandPaletteOpen: boolean;
  sidebarCollapsed: boolean;
  setCommandPaletteOpen: (open: boolean) => void;
  toggleSidebar: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  commandPaletteOpen: false,
  sidebarCollapsed: false,
  setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
  toggleSidebar: () =>
    set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
}));
