import type { ReactNode } from "react";

import { DashboardShell } from "@/components/dashboard/DashboardShell";

/** Protected dashboard layout (auth enforced in proxy.ts). */
export default function DashboardLayout({ children }: { children: ReactNode }) {
  return <DashboardShell>{children}</DashboardShell>;
}
