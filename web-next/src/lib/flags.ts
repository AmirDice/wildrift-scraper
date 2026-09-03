// Feature flags.
//
// BUILD_TOOLS_LIVE gates the Build Optimizer (/build) and Counter Builder
// (/counter). They are finished but held back from production for a separate
// launch. When off they are hidden everywhere at once: nav links, landing-page
// flagship cards, the top feature banner, the footer CTA, the per-champion
// recommended build, the sitemap, and the pages themselves (which redirect
// home).
//
// LAUNCHED. The default is now ON everywhere, including preview and production
// deployments; it used to be OFF unless NODE_ENV was development.
//
// The flag is kept rather than deleted, because it is still the kill switch:
// set NEXT_PUBLIC_BUILD_TOOLS=0 in the Vercel environment and redeploy to pull
// both tools back behind the curtain without touching code. Only an explicit
// "0" or "false" turns them off; anything else, including unset, is ON.
//
// NEXT_PUBLIC_ vars are inlined at build time, so this works in both server and
// client components -- and so a change to it needs a redeploy, not just a
// restart.
const _flag = process.env.NEXT_PUBLIC_BUILD_TOOLS?.toLowerCase();

export const BUILD_TOOLS_LIVE = !(_flag === "0" || _flag === "false");

// DRAFT_TOOL_LIVE gates the Draft Assistant (/draft) SEPARATELY from the rest
// of the build tools, which are launched and must stay up.
//
// It is held back while the draft flow is still being tested against real
// lobbies: the page, its nav entry and its sitemap entry all disappear
// together, and the route redirects home. Local development keeps it on, which
// is where the testing happens.
//
// Turn it on in production by setting NEXT_PUBLIC_DRAFT_TOOL=1 in the Vercel
// environment and redeploying, or by flipping this default once the tool has
// earned it. NEXT_PUBLIC_ vars are inlined at build time, so either way it
// needs a redeploy rather than a restart.
const _draftFlag = process.env.NEXT_PUBLIC_DRAFT_TOOL?.toLowerCase();

export const DRAFT_TOOL_LIVE =
  _draftFlag === "1" || _draftFlag === "true"
    ? true
    : _draftFlag === "0" || _draftFlag === "false"
      ? false
      : process.env.NODE_ENV === "development";

// OVERLAY_DOWNLOAD_LIVE gates the APK download on /overlay, and ONLY that.
// The page itself is always public: it is the thing people are pointed at from
// Discord and YouTube, and it collects the notify list, both of which work
// before there is anything to download.
//
// It is off by default on purpose. Handing out an APK is a one-way door in a
// way that shipping a web page is not: the signing key you publish first is
// the key you are stuck with, because Android refuses to update an app whose
// signature changed and the only way out is asking every user to uninstall.
// So the download stays shut until there is a release build signed with a key
// that is kept, rather than the throwaway debug keystore build.bat generates
// when it cannot find one.
//
// Open it with NEXT_PUBLIC_OVERLAY_DOWNLOAD=1 and a redeploy.
const _overlayFlag = process.env.NEXT_PUBLIC_OVERLAY_DOWNLOAD?.toLowerCase();

export const OVERLAY_DOWNLOAD_LIVE = _overlayFlag === "1" || _overlayFlag === "true";

/** Filename served from /public. Kept here so the page and the build script
 *  cannot drift apart silently. */
export const OVERLAY_APK = "/wrtruemeta-overlay.apk";
export const OVERLAY_VERSION = "2.5";

/**
 * Champions whose Recommended Builds tab is open.
 *
 * The generated catalogue still needs validating, so the curated tab is held
 * back per champion rather than as a whole: everything else in the studio --
 * the Personal Build Generator, the Custom Build Lab and the Counter Builder --
 * is live, because those compute an answer for the player rather than serving a
 * pre-authored one we have not finished checking.
 *
 * Hecarim stays open deliberately. He is the landing page's example, and a
 * visitor who follows it should reach a real build rather than a locked tab.
 *
 * Opening the rest is a one-line change: add the name, or return true here.
 */
const RECOMMENDED_BUILDS_OPEN = new Set(["Hecarim"]);

export function recommendedBuildsLive(championName: string): boolean {
  return RECOMMENDED_BUILDS_OPEN.has(championName);
}
