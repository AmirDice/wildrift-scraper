/**
 * Log a HANDLED server error and send it to Sentry.
 *
 * onRequestError (src/instrumentation.ts) only sees errors that escape a
 * route. The ones that matter most here are caught on purpose so the visitor
 * gets a clean message: a failed advisor generation, a Stripe call, a webhook
 * that could not grant credits. Those used to reach only console.error, so
 * this keeps the log line and also reports them.
 *
 * Awaited by callers because a serverless function can freeze as soon as the
 * response is sent, taking an unsent event with it. Without SENTRY_DSN it is
 * exactly the old console.error.
 */
export async function reportError(message: string, error?: unknown): Promise<void> {
  console.error(message, error);
  if (!process.env.SENTRY_DSN || process.env.NEXT_RUNTIME !== "nodejs") return;
  try {
    const Sentry = await import("@sentry/nextjs");
    if (error instanceof Error) {
      Sentry.captureException(error, { extra: { context: message } });
    } else {
      Sentry.captureMessage(message, {
        level: "error",
        extra: { detail: typeof error === "string" ? error.slice(0, 2000) : error },
      });
    }
    await Sentry.flush(2000);
  } catch {
    // Monitoring must never turn a handled error into an unhandled one.
  }
}
