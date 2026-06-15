import type { ReactNode } from "react";

import { AppShell } from "@/components/app/AppShell";

/** Authenticated app group (auth enforced in proxy.ts). */
export default function AppGroupLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
