/* Ranked tier emblems, shared by anything that shows a player's rank.
 *
 * Two ladders live here. The standard one (Iron..Sovereign) uses the Season
 * 2019 crests plus the Wild Rift Emerald/Sovereign art; the Legendary Ranked
 * queue runs its own tiers with owner-supplied art. They are NOT one ordered
 * ladder, so callers that group by tier should keep them apart -- see the
 * leaderboard's two spreads.
 */

const TIER_ICONS: Record<string, string> = {
  iron: "iron.webp", bronze: "bronze.webp", silver: "silver.webp",
  gold: "gold.webp", platinum: "platinum.webp", emerald: "emerald.webp",
  diamond: "diamond.webp", master: "master.webp", grandmaster: "grandmaster.webp",
  challenger: "challenger.webp", sovereign: "sovereign.webp",
  "legendary-master": "legendary-master.png",
  "legendary-grandmaster": "legendary-grandmaster.png",
  "legendary-challenger": "legendary-challenger.png",
  "legendary-commander": "legendary-commander.png",
  legend: "legend.png",
};

export function tierParts(tier: string): { family: string; roman: string } {
  // Hyphens survive and split like spaces, so this is idempotent on a family
  // key it produced earlier ("legendary-grandmaster" parses back to itself).
  // Callers group by family and then hand that key straight back here to draw
  // the emblem; when the hyphen was stripped the key became
  // "legendarygrandmaster", matched no art, and fell back to a text chip.
  const words = tier.trim().toLowerCase().replace(/[^a-z\s-]/g, "")
    .split(/[\s-]+/).filter(Boolean);
  let family = words[0] ?? "";
  // Legendary Ranked tiers are two words ("Legendary Grandmaster IV");
  // "Legend" and "Ascended Legend" share the Legend art.
  if (family === "legendary" && words[1]) family = `legendary-${words[1]}`;
  if (family === "ascended") family = "legend";
  const roman = tier.match(/\b(I{1,3}|IV|V)\b/)?.[1] ?? "";
  return { family, roman };
}

/** True for a Legendary Ranked tier, which is a separate queue's ladder. */
export const isLegendaryTier = (tier: string) =>
  tierParts(tier).family.startsWith("legendary");

/* Ordering, for anything that has to SORT by tier.
 *
 * The two ladders are not one ladder, which is why nothing above tries to rank
 * them together. A sort needs a total order anyway, so this is the deliberate
 * choice: the Legendary Ranked tiers sit ABOVE the whole standard ladder,
 * because that queue is entered from the top of the standard one. Anything
 * grouping rather than sorting should still keep them apart.
 *
 * Iron through Platinum are listed for completeness and never appear in
 * practice -- every row here is a top-50 player on some champion, and the
 * lowest tier the scrape has ever recorded is Diamond.
 */
const TIER_ORDER = [
  "iron", "bronze", "silver", "gold", "platinum", "emerald",
  "diamond", "master", "grandmaster", "challenger", "sovereign",
  "legend",
  "legendary-master", "legendary-grandmaster",
  "legendary-challenger", "legendary-commander",
];

const ROMAN_VALUE: Record<string, number> = { I: 1, II: 2, III: 3, IV: 4, V: 5 };

/**
 * A sortable ordinal for a tier string. Higher is better. Null when the tier
 * is absent or unrecognised, so callers can sort those last rather than
 * treating an unknown tier as the bottom of the ladder.
 *
 * Divisions count DOWN inside a tier (Diamond IV is the entry, Diamond I the
 * exit), so the roman numeral is inverted. Challenger and Sovereign carry no
 * numeral because they are single divisions.
 */
export function tierRank(tier: string | null | undefined): number | null {
  if (!tier) return null;
  const { family, roman } = tierParts(tier);
  const base = TIER_ORDER.indexOf(family);
  if (base < 0) return null;
  return base * 10 + (6 - (ROMAN_VALUE[roman] ?? 0));
}

export function TierBadge({ tier, size = 18 }: { tier: string; size?: number }) {
  const { family, roman } = tierParts(tier);
  const icon = TIER_ICONS[family];
  if (icon) {
    return (
      <span className="inline-flex items-center gap-0.5" title={tier}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`/tiers/${icon}`}
          alt={tier}
          width={size}
          height={size}
          loading="lazy"
          className="shrink-0 object-contain"
          style={{ width: size, height: size }}
        />
        {roman && <span className="text-[0.6rem] font-bold text-muted">{roman}</span>}
      </span>
    );
  }
  return (
    <span className="rounded bg-white/10 px-1 py-px text-[0.6rem] font-bold text-muted" title={tier}>
      {tier}
    </span>
  );
}
