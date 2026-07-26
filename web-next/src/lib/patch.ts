import statRules from "@/data/stat_rules.json";

/**
 * The patch the site's data describes.
 *
 * People search for "wild rift tier list patch 7.2a", not "wild rift tier
 * list", so the patch belongs in titles, descriptions and on the page itself.
 * That only works if it is true, and a version string copy-pasted into six
 * files goes stale in five of them. It is therefore read from the same
 * stat_rules.json the item and rune data is validated against: when the
 * pipeline moves to the next patch, every page follows automatically.
 */
export const CURRENT_PATCH = (statRules as { targetPatch?: string }).targetPatch ?? "";

/** "patch 7.2a", or an empty string when the data has no patch recorded. */
export const patchLabel = CURRENT_PATCH ? `patch ${CURRENT_PATCH}` : "";
