"use client";

import { useEffect } from "react";
import { reportClientError } from "@/lib/client-errors";

/**
 * Last-resort error screen: shown when a render error escapes every other
 * boundary. It replaces the root layout, so it carries its own html, body and
 * inline styles. The error goes to Sentry (lib/client-errors.ts).
 */
export default function GlobalError({ error, unstable_retry }: { error: Error & { digest?: string }; unstable_retry: () => void }) {
  useEffect(() => {
    reportClientError(error, { kind: "render", ...(error.digest ? { digest: error.digest } : {}) });
  }, [error]);

  return (
    <html lang="en">
      <body style={{ margin: 0, minHeight: "100vh", display: "grid", placeItems: "center", background: "#0b0f17", color: "#e7ecf5", fontFamily: "system-ui, sans-serif" }}>
        <main style={{ maxWidth: 420, padding: 24, textAlign: "center" }}>
          <h1 style={{ fontSize: 22, margin: "0 0 8px" }}>Something broke on this page</h1>
          <p style={{ margin: "0 0 20px", color: "#9aa6b8", lineHeight: 1.5 }}>
            The error has been reported. Try again, or go back to the home page.
          </p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center" }}>
            <button onClick={() => unstable_retry()} style={{ padding: "10px 18px", borderRadius: 10, border: 0, background: "#5b8cff", color: "#fff", fontWeight: 600, cursor: "pointer" }}>
              Try again
            </button>
            <a href="/" style={{ padding: "10px 18px", borderRadius: 10, border: "1px solid #2a3344", color: "#e7ecf5", textDecoration: "none", fontWeight: 600 }}>
              Home
            </a>
          </div>
        </main>
      </body>
    </html>
  );
}
