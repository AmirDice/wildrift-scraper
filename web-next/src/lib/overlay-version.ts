/**
 * Which builds of the Android overlay the API still serves.
 *
 * Every overlay build before 3.2-alpha (versionCode 32) is deprecated: they
 * sent no version at all, so "no version" and "too old" are the same answer.
 * Raise MIN_OVERLAY_VERSION to retire the next generation; the app reports
 * its manifest versionCode, so no other constant has to move.
 *
 * Three endpoints, three ways of knowing the caller is the app:
 *   - /api/v1/bundle is fetched by the app alone and is CDN-cached, so the
 *     version rides in the URL (?app=32). A header would not do: the cache
 *     would hand one version's answer to another.
 *   - /api/v1/activate is app-only and uncached: the x-app-version header.
 *   - /api/v1/build is shared with the /draft page, so only a caller that
 *     looks like the app (that header, or the Dalvik user agent of Android's
 *     HTTP client, which every old build sends) is held to the minimum.
 *     Browsers send a Mozilla user agent and are never refused here.
 *
 * Old builds show the `error` text in red where a build would appear, so the
 * message is what an outdated player actually reads.
 */
export const MIN_OVERLAY_VERSION = 32;

export const OVERLAY_UPDATE_MESSAGE =
  "This version of the WrTrueMeta overlay is out of date. Get the new one from "
  + "wrtruemeta.com/overlay or the Discord to keep getting builds.";

function versionOf(raw: string | null | undefined): number {
  const n = Number.parseInt(String(raw ?? ""), 10);
  return Number.isFinite(n) ? n : 0;
}

/** For app-only endpoints: anything below the minimum, including no version. */
export function appVersionTooOld(raw: string | null | undefined): boolean {
  return versionOf(raw) < MIN_OVERLAY_VERSION;
}

/** For the shared build endpoint: refuse only callers that are the app. */
export function outdatedOverlay(request: Request): boolean {
  const header = request.headers.get("x-app-version");
  const fromApp = header !== null || /dalvik/i.test(request.headers.get("user-agent") ?? "");
  return fromApp && appVersionTooOld(header);
}

export function outdatedBody() {
  return { error: OVERLAY_UPDATE_MESSAGE, updateRequired: true, minVersion: MIN_OVERLAY_VERSION };
}
