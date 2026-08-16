import changeHistory from "@/data/champion_change_history.json";
import itemChanges from "@/data/patch_item_changes.json";
import { CURRENT_PATCH } from "@/lib/patch";
import { getBuildsFor, visibleBuildVariants } from "@/lib/builds";

/**
 * WHY a champion is moving: the patch-note paper trail behind a win-rate swing.
 *
 * Two honest signals, checked in order:
 *  - the champion was changed directly this patch (the change history has the
 *    per-champion balance entry, summary included);
 *  - the champion's recommended builds lean on items this patch touched (the
 *    curated item-change overlay, transcribed from the official notes).
 * A mover with neither is still real movement -- meta drift, counters rising
 *  or falling around them -- but the page should say "no direct change" rather
 * than invent a cause.
 *
 * The direction chip is INFERRED from the summary's own framing and stays
 * "adjusted" whenever the wording cuts both ways: a wrong chip is worse than a
 * vague one.
 */

type HistoryEntry = {
  patch: string;
  kind: string;
  modeOnly?: boolean;
  summary?: string;
  changes?: { ability?: string; text?: string }[];
};

const HISTORY = (changeHistory as { champions: Record<string, HistoryEntry[]> }).champions;
const ITEMS = itemChanges as {
  patch: string;
  items: { slug: string; name: string; direction: "buff" | "nerf"; text: string }[];
};
const CHANGED_ITEM = new Map(ITEMS.items.map((i) => [i.slug, i]));

export type MoverWhy = {
  /** The champion's own 7.2c balance entry, when there is one. */
  direct?: { direction: "buff" | "nerf" | "adjusted"; summary: string; changeCount: number };
  /** Changed items this champion's recommended builds actually carry. */
  items: { name: string; direction: "buff" | "nerf"; text: string }[];
};

const BUFF_WORDS = /underperform|struggl|falling short|falling behind|improv|boost|buff|strengthen|bring (him|her|it|them) back|giving .{0,24}(love|help)/i;
const NERF_WORDS = /dominat|too (much|strong|durable|effective|difficult to keep|safe|reliable|oppressive)|reduc|trim|toning down|nerf|rein(ing)? in|dial(ing)? back|thriving|overperform/i;

function direction(summary: string): "buff" | "nerf" | "adjusted" {
  const buff = BUFF_WORDS.test(summary);
  const nerf = NERF_WORDS.test(summary);
  if (buff && !nerf) return "buff";
  if (nerf && !buff) return "nerf";
  return "adjusted";
}

/** Every item slug the champion's visible recommended builds equip. */
function buildItemSlugs(championName: string): Set<string> {
  const slugs = new Set<string>();
  const data = getBuildsFor(championName);
  if (!data) return slugs;
  for (const variant of visibleBuildVariants(data)) {
    const build = data.builds[variant];
    if (!build) continue;
    for (const item of build.coreBuild ?? []) slugs.add(item.slug);
    if (build.boots?.slug) slugs.add(build.boots.slug);
    if (build.bootsEarly?.slug) slugs.add(build.bootsEarly.slug);
    if (build.enchantment?.slug) slugs.add(build.enchantment.slug);
  }
  return slugs;
}

/** The paper trail for one mover, or null when the overlay is for another patch. */
export function moverWhy(championName: string): MoverWhy | null {
  if (!CURRENT_PATCH || ITEMS.patch !== CURRENT_PATCH) return null;

  const why: MoverWhy = { items: [] };

  // modeOnly excluded: an ARAM buff explains nothing about a ranked board.
  const entry = (HISTORY[championName] ?? []).find(
    (e) => e.patch === CURRENT_PATCH && e.kind === "balance" && !e.modeOnly,
  );
  if (entry) {
    const summary = (entry.summary ?? "").trim()
      // Entries from the legacy article carry no prose; the touched abilities
      // are still a truthful tooltip.
      || (entry.changes ?? []).map((c) => c.ability).filter(Boolean).join(" · ");
    why.direct = {
      direction: entry.summary?.trim() ? direction(entry.summary) : "adjusted",
      summary,
      changeCount: entry.changes?.length ?? 0,
    };
  }

  const inBuilds = buildItemSlugs(championName);
  for (const slug of inBuilds) {
    const changed = CHANGED_ITEM.get(slug);
    if (changed) why.items.push({ name: changed.name, direction: changed.direction, text: changed.text });
  }
  why.items.sort((a, b) => a.name.localeCompare(b.name));
  return why;
}
