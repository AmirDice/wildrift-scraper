/**
 * Browser error reporting (Sentry), loaded only when an error happens.
 *
 * The browser SDK is ~70KB, and this is an ad-funded site where every page
 * load counts, so nothing is downloaded up front: the first real error pulls
 * in the SDK, initialises it, and sends that error. Visitors who never hit an
 * error never download it.
 *
 * Same privacy line as the server (src/instrumentation.ts): no cookies, no
 * query strings, no user info. Default integrations are off, so the SDK does
 * not hook globals or record breadcrumbs of what the visitor clicked or typed;
 * src/instrumentation-client.ts decides what gets reported.
 */
const DSN = process.env.NEXT_PUBLIC_SENTRY_DSN;
const ENVIRONMENT = process.env.NEXT_PUBLIC_SENTRY_ENV || "development";

// A crashing render loop can throw hundreds of times; a handful per page view
// says everything and keeps the free quota for other visitors.
const MAX_PER_PAGE = 5;
let sent = 0;
let sdk: Promise<typeof import("@sentry/nextjs") | null> | null = null;

function load() {
  sdk ??= import("@sentry/nextjs")
    .then((Sentry) => {
      Sentry.init({
        dsn: DSN,
        environment: ENVIRONMENT,
        defaultIntegrations: false,
        integrations: [Sentry.dedupeIntegration(), Sentry.httpContextIntegration()],
        tracesSampleRate: 0,
        beforeSend(event) {
          if (event.request?.url) event.request.url = event.request.url.split("?")[0];
          if (event.request) {
            delete event.request.cookies;
            delete event.request.query_string;
          }
          delete event.user;
          return event;
        },
      });
      return Sentry;
    })
    .catch(() => null);
  return sdk;
}

/** Noise that is not the site's fault: extensions, ad scripts, old browsers. */
function isNoise(error: unknown): boolean {
  const text = error instanceof Error ? `${error.message}\n${error.stack ?? ""}` : String(error);
  return /ResizeObserver loop|chrome-extension:|moz-extension:|safari-extension:|adsbygoogle|googlesyndication|Script error\.?$|Load failed|NetworkError when attempting|Failed to fetch|AbortError|The operation was aborted/i.test(text);
}

export function reportClientError(error: unknown, context?: Record<string, string>) {
  if (!DSN || typeof window === "undefined" || sent >= MAX_PER_PAGE || isNoise(error)) return;
  sent += 1;
  void load().then((Sentry) => {
    if (!Sentry) return;
    Sentry.withScope((scope) => {
      scope.setTag("side", "browser");
      if (context) for (const [k, v] of Object.entries(context)) scope.setTag(k, v);
      Sentry.captureException(error instanceof Error ? error : new Error(String(error)));
    });
  });
}
