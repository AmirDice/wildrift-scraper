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
 * this is the patch whose live ladder boards are about to be refreshed.
 */

/**
 * Applied to the item and ability data, deliberately NOT given a ladder
 * collection. Those are two different things and the copy must keep them
 * apart: every number a patch changes directly (ability ratios, cooldowns,
 * item stats) is on this patch, and only the measured win rates are not.
 */
export const SKIPPED_PATCH = "7.3a";

/** The patch whose games the win rates were actually collected from. */
export const WINRATE_PATCH = "7.2d";

/** The patch the next collection and the next round of work is aimed at. */
export const NEXT_PATCH = "7.3a";

/** The announced window for the next EU/NA/CN ladder collection. */
export const COLLECTION_START = "Monday, October 5, 2026";
export const COLLECTION_EXPECTED_FINISH = "Wednesday, October 7, 2026";
export const COLLECTION_REGIONS = "EU, NA and CN";

export const ANNOUNCEMENT = {
  /** Bump when the message changes, so a dismissed banner comes back. */
  key: "wtm-announce-collection-2026-10-v1",
  href: "/updates",
  lead: "Regional data collection starts Monday",
  short: `${COLLECTION_REGIONS} ladder data collection starts ${COLLECTION_START} and is expected to finish ${COLLECTION_EXPECTED_FINISH}. Win rates and builds will update as each region completes.`,
  cta: "See the schedule",
  badges: ["Data refresh"],
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
    date: "1 October 2026",
    title: "Regional data collection scheduled",
    body:
      `${COLLECTION_REGIONS} collection begins ${COLLECTION_START} and is expected `
      + `to finish ${COLLECTION_EXPECTED_FINISH}. The ladder boards will update as `
      + "each region is completed; until then, the current boards remain visible.",
  },
  {
    date: "29 September 2026",
    title: `Patch ${SKIPPED_PATCH} applied: balance follow-up`,
    body:
      "Hwei's damage was reduced, Samira, Tristana, Draven and Viego were "
      + "buffed, and Rammus, Malphite, Caitlyn, Senna, Syndra, Swain and Yuumi "
      + "were adjusted. Yun Tal Wildarrows now has 35% Attack Speed and a 25s "
      + "Flurry cooldown, Whispering Circlet and Diadem of Songs use 0.25% "
      + "Harmony, Death's Dance costs 3300 gold, Smite burns for less early, and "
      + "the post-plating turret resistance window and main crystal health were reduced."
      + ` Win rates remain on the ${WINRATE_PATCH} boards until the next collection.`,
  },
  {
    date: "21 September 2026",
    title: `Patch ${SKIPPED_PATCH} applied: the marksman overhaul`,
    body:
      "Ten items joined the shop (Yun Tal Wildarrows, Stormrazor, Rapid Firecannon, "
      + "Fiendhunter Bolts, Hexoptics C44, Immortal Shieldbow, Statikk Shiv, Echoes of "
      + "Helia, Whispering Circlet, Diadem of Songs) and three left it: Magnetic "
      + "Blaster, Soul Transfer and Searing Crown. Base critical strike damage is 200% "
      + "instead of 175%, the attack speed cap is 3, and Lifesteal is a new stat that "
      + "heals from attacks only. Legend: Tenacity became Legend: Haste and Ingenious "
      + "Hunter is gone. Thirty-two champions changed abilities, and every champion in "
      + "the game has new attack speed numbers, so the damage and build figures across "
      + "the site have all moved. Win rates are still measured on the "
      + `${WINRATE_PATCH} boards until the next collection.`,
  },
  {
    date: "18 September 2026",
    title: "The Draft Assistant is live",
    body:
      "Track champion select as it happens: tap a slot to fill it, tap again to "
      + "clear it, for all ten bans and both teams. It suggests what to pick from "
      + "the champions you actually play, reads what their comp is built to do, "
      + "and turns their five into a counter build with one tap. On a PC it can "
      + "also read a mirrored phone screen, so nothing has to be tapped at all.",
  },
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
