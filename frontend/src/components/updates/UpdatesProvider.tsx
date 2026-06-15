"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { getLatestAnnouncement, type Feature } from "@/config/registry";
import {
  getFirstSeen,
  isWithinWindow,
  setFirstSeen,
} from "@/lib/updates/storage";
import { WhatsNewModal } from "./WhatsNewModal";

interface UpdatesContextValue {
  announcement: Feature | null;
  /** Unseen or within the 24h window — drives the orb pulse. */
  updateAvailable: boolean;
  open: boolean;
  openModal: () => void;
  closeModal: () => void;
}

const UpdatesContext = createContext<UpdatesContextValue | undefined>(
  undefined,
);

export function UpdatesProvider({ children }: { children: ReactNode }) {
  const announcement = useMemo(() => getLatestAnnouncement(), []);
  const [state, setState] = useState<{ available: boolean; open: boolean }>({
    available: false,
    open: false,
  });

  useEffect(() => {
    if (!announcement) return;
    const seen = getFirstSeen(announcement.id);
    let available = false;
    let open = false;
    if (seen === null) {
      // First time after this update → record + auto-announce.
      setFirstSeen(announcement.id, Date.now());
      available = true;
      open = true;
    } else if (isWithinWindow(seen)) {
      available = true;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState({ available, open });
  }, [announcement]);

  const value = useMemo<UpdatesContextValue>(
    () => ({
      announcement,
      updateAvailable: state.available,
      open: state.open,
      openModal: () => setState((s) => ({ ...s, open: true })),
      closeModal: () => setState((s) => ({ ...s, open: false })),
    }),
    [announcement, state],
  );

  return (
    <UpdatesContext.Provider value={value}>
      {children}
      <WhatsNewModal />
    </UpdatesContext.Provider>
  );
}

export function useUpdates() {
  const ctx = useContext(UpdatesContext);
  if (!ctx) throw new Error("useUpdates must be used within <UpdatesProvider>");
  return ctx;
}
