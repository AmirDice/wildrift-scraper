import { reportClientError } from "@/lib/client-errors";

/**
 * Uncaught browser errors and unhandled promise rejections go to Sentry
 * (lib/client-errors.ts loads the SDK only when one happens). Errors React
 * catches in a boundary are reported by app/global-error.tsx.
 *
 * Only errors from this site's own scripts: a cross-origin script (ads,
 * extensions) reports a bare "Script error." with no stack, which is noise.
 */
try {
  window.addEventListener("error", (event) => {
    if (!event.error) return;
    if (event.filename && !event.filename.startsWith(window.location.origin)) return;
    reportClientError(event.error, { kind: "uncaught" });
  });
  window.addEventListener("unhandledrejection", (event) => {
    reportClientError(event.reason, { kind: "unhandledrejection" });
  });
} catch {
  // Monitoring must never break the page.
}
