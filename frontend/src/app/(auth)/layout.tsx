import type { ReactNode } from "react";

/** Public auth route group — centered over the global ambient background. */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-1 items-center justify-center px-6 py-12">
      {children}
    </div>
  );
}
