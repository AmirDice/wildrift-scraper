/**
 * The one thing the site is currently telling everybody.
 *
 * Three surfaces say this: the banner across the top of every page, the
 * /updates page it points at, and the notice on the pages that actually show
 * win rates. They were going to drift the moment one of them was edited and
 * the other two were not, which is exactly how a site ends up promising a data
 * refresh it has already decided not to run. So it lives here once.
 *
 * `SKIPPED_PATCH` is deliberately separate from CURRENT_PATCH in lib/patch.ts.
 * CURRENT_PATCH is what the DATA describes and is read from stat_rules.json;
 * this is a patch that exists in the game and that the site has chosen not to
 * follow. Naming it is the honest move: a reader who knows 7.2e is live and
 * sees a page headed 7.2d should be told that gap is a decision, not a
 * failure to keep up.
 */

/**
 * Applied to the item and ability data, deliberately NOT given a ladder
 * collection. Those are two different things and the copy must keep them
 * apart: every number a patch changes directly (ability ratios, cooldowns,
 * item stats) is on this patch, and only the measured win rates are not.
 */
export const SKIPPED_PATCH = "7.2e";

/** The patch whose games the win rates were actually collected from. */
export const WINRATE_PATCH = "7.2d";

/** The patch the next collection and the next round of work is aimed at. */
export const NEXT_PATCH = "7.3";

export const ANNOUNCEMENT = {
  /** Bump when the message changes, so a dismissed banner comes back. */
  key: "wtm-announce-skip-72e-v1",
  href: "/updates",
  lead: `Patch ${SKIPPED_PATCH} is live`,
  short: `Items, abilities and champion changes are updated. Win rates stay on the ${WINRATE_PATCH} boards: the next collection is for ${NEXT_PATCH}, and the time goes into new features instead.`,
  cta: "Read why",
  badges: ["Update"],
  /** Pages the banner points at, so it does not appear on top of itself. */
  hideOn: ["/updates"],
} as const;

/**
 * Dated record of changes worth telling a reader about.
 *
 * Newest first. This exists so a correction to the numbers is visible rather
 * than silent: someone who screenshotted a damage figure last week and sees a
 * different one today deserves to find out why in one click. Keep entries
 * short, specific and honest about direction -- "was over-counting" reads as
 * trustworthy, "improvements to our algorithm" does not.
 */
export const CHANGELOG: { date: string; title: string; body: string }[] = [
  {
    date: "11 September 2026",
    title: "Basic attack damage corrected for nine champions",
    body:
      "The fight engine was charging a normal basic attack on top of kits whose "
      + "passive IS the attack, so Graves' shotgun, Ashe's Frost Shot, Renekton's "
      + "empowered strike and six others were counted roughly twice. Graves read "
      + "2.44 times his attack damage per auto where the game says 1.44. Crit was "
      + "affected in both directions: it never reached Graves' actual shotgun, and "
      + "Ashe was being given critical strike damage she does not have. Build "
      + "recommendations are unchanged, because those come from the model rather "
      + "than the engine. The damage figures shown beside them are now accurate.",
  },
  {
    date: "11 September 2026",
    title: `Patch ${SKIPPED_PATCH} applied to items and abilities`,
    body:
      `Vi, Janna, Swain, Nautilus and Malphite, plus Eclipse, Unending Despair `
      + `and Seeker's Armguard. Win rates stay on the ${WINRATE_PATCH} boards; see `
      + `above for why.`,
  },
];
