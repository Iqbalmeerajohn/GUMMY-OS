import type { ReactNode } from "react";

import { AppHeader } from "@/components/app/AppHeader";

/** Full-height workspace chrome (auth enforced in proxy.ts). */
export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-[100svh] flex-col">
      <AppHeader />
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}
