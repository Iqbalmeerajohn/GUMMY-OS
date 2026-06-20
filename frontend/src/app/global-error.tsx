"use client";

import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";

/**
 * Root error boundary. Next.js renders this when an error escapes the root
 * layout — the last line of defence for client/render crashes. We forward the
 * error to Sentry (a no-op when monitoring is disabled) and show a minimal,
 * recoverable fallback. `global-error` must render its own <html>/<body>.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: "1rem",
          fontFamily: "system-ui, sans-serif",
          background: "#0a0a0a",
          color: "#fafafa",
          textAlign: "center",
          padding: "2rem",
        }}
      >
        <h1 style={{ fontSize: "1.25rem", fontWeight: 600 }}>
          Something went wrong
        </h1>
        <p style={{ color: "#a1a1aa", maxWidth: "28rem" }}>
          GUMMY hit an unexpected error. The issue has been reported. You can
          try again.
        </p>
        <button
          onClick={reset}
          style={{
            borderRadius: "0.625rem",
            border: "1px solid #3f3f46",
            background: "#fafafa",
            color: "#0a0a0a",
            padding: "0.5rem 1.25rem",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
