import { Badge } from "@/components/ui/badge";
import { POSITIONING } from "@/config";

/**
 * M0 scaffold splash — a minimal branded surface that verifies the theme,
 * component primitives, and config registry render. The real Landing,
 * onboarding, and Discover experiences are built in M2 from this config.
 */
export default function Home() {
  return (
    <main className="relative flex flex-1 flex-col items-center justify-center overflow-hidden px-6 py-24">
      {/* Gummy orb */}
      <div
        className="bg-primary gummy-glow mb-10 size-20 rounded-full"
        aria-hidden
      />

      <Badge variant="secondary" className="mb-6">
        M0 · scaffold ready
      </Badge>

      <h1 className="text-center text-4xl font-semibold tracking-tight sm:text-5xl">
        GUMMY
      </h1>
      <p className="text-muted-foreground mt-3 max-w-md text-center text-lg">
        Your Personal AI Operating System
      </p>

      <div className="mt-10 flex max-w-2xl flex-wrap justify-center gap-2">
        {POSITIONING.map((p) => (
          <span
            key={p.label}
            className="border-border bg-card text-card-foreground rounded-full border px-3 py-1 text-sm"
          >
            {p.label}
          </span>
        ))}
      </div>
    </main>
  );
}
