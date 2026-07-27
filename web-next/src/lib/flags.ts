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
