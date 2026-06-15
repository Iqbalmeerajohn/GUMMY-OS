import Link from "next/link";
import type { ReactNode } from "react";

import { LivingOrb } from "@/components/brand/LivingOrb";

/**
 * Shared shell for auth screens — a centered glass card crowned by the Living
 * Orb. Keeps login / signup / forgot-password visually consistent and premium.
 */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="flex w-full max-w-sm flex-col items-center">
      <Link href="/" aria-label="GUMMY home" className="mb-8">
        <LivingOrb size={72} state="idle" />
      </Link>

      <div className="glass elevation-3 w-full rounded-3xl p-7 sm:p-8">
        <h1 className="font-heading text-center text-2xl font-semibold tracking-tight">
          {title}
        </h1>
        {subtitle ? (
          <p className="text-muted-foreground mt-2 text-center text-sm text-balance">
            {subtitle}
          </p>
        ) : null}
        <div className="mt-6">{children}</div>
      </div>

      {footer ? (
        <div className="text-muted-foreground mt-6 text-center text-sm">
          {footer}
        </div>
      ) : null}
    </div>
  );
}
