// Feature flags.
//
// BUILD_TOOLS_LIVE gates the Build Optimizer (/build) and Counter Builder
// (/counter). They are finished but held back from production for a separate
// launch. When off they are hidden everywhere at once: nav links, landing-page
// flagship cards, the top feature banner, the footer CTA, the per-champion
// recommended build, the sitemap, and the pages themselves (which redirect
// home).
//
// Resolution order:
//   1. NEXT_PUBLIC_BUILD_TOOLS = "1" | "true"  -> force ON  (set in .env.local
//      for local dev so the tools are always reachable while developing).
//   2. NEXT_PUBLIC_BUILD_TOOLS = "0" | "false" -> force OFF.
//   3. unset -> ON in local dev (next dev), OFF everywhere else (production).
//
// NEXT_PUBLIC_ vars are inlined at build time, so this works in both server and
// client components. To LAUNCH in production, set NEXT_PUBLIC_BUILD_TOOLS=1 in
// the Vercel environment (or just hard-code this to `true`).
const _flag = process.env.NEXT_PUBLIC_BUILD_TOOLS?.toLowerCase();

export const BUILD_TOOLS_LIVE =
  _flag === "1" || _flag === "true"
    ? true
    : _flag === "0" || _flag === "false"
      ? false
      : process.env.NODE_ENV !== "production";
