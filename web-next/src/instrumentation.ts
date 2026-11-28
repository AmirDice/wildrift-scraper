import type { Instrumentation } from "next";

/**
 * Server error tracking (Sentry).
 *
 * Before this, a route that threw only left a line in the Vercel function log,
 * and nobody reads those unless a user complains. Sentry groups the errors,
 * emails on a new one, and keeps the stack trace.
 *
 * Inert without SENTRY_DSN: local dev and preview builds without the variable
 * report nothing, so this cannot break a build or spam the project.
 *
 * Server only, on purpose. The browser SDK adds about 70KB to every page of an
 * ad-funded site; client errors can be added later if server errors turn out
 * not to be the whole story.
 *
 * Privacy: no PII. Cookies, auth headers and IPs are stripped before anything
 * leaves the function (the session cookie identifies a signed-in account).
 */
const DSN = process.env.SENTRY_DSN;

export async function register() {
  if (!DSN || process.env.NEXT_RUNTIME !== "nodejs") return;
  const Sentry = await import("@sentry/nextjs");
  Sentry.init({
    dsn: DSN,
    environment: process.env.VERCEL_ENV ?? "development",
    release: process.env.VERCEL_GIT_COMMIT_SHA,
    // SDK v11 collects cookies, headers, query strings and bodies by DEFAULT.
    // Turn all of it off: the session cookie names an account, the admin
    // readout takes its token as a query parameter, and request bodies are
    // what visitors typed.
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: { request: { allow: ["user-agent", "referer", "content-type"] }, response: false },
      httpBodies: [],
      urlQueryParams: false,
      genAI: { inputs: false, outputs: false },
    },
    // Every trace locally, a tenth in production: enough to see which
    // routes are slow without spending the span quota on every page view.
    tracesSampleRate: process.env.VERCEL_ENV === "production" ? 0.1 : 1.0,
    // Logs: in SDK v11 Sentry.logger.* is on by default; the enableLogs
    // flag from v9/v10 no longer exists.
    beforeSend(event) {
      if (event.request) {
        delete event.request.cookies;
        delete event.request.query_string;
        if (event.request.url) event.request.url = event.request.url.split("?")[0];
        const headers = event.request.headers;
        if (headers) {
          for (const name of Object.keys(headers)) {
            if (/^(cookie|authorization|x-advisor-secret|x-forwarded-for|x-real-ip)$/i.test(name)) {
              delete headers[name];
            }
          }
        }
      }
      if (event.user) event.user = { id: event.user.id };
      return event;
    },
  });
}

export const onRequestError: Instrumentation.onRequestError = async (...args) => {
  if (!DSN || process.env.NEXT_RUNTIME !== "nodejs") return;
  const Sentry = await import("@sentry/nextjs");
  Sentry.captureRequestError(...args);
  // Serverless functions can freeze as soon as the response is sent; flush so
  // the event is not lost with them.
  await Sentry.flush(2000);
};
