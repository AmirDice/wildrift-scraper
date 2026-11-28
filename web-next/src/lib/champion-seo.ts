/**
 * Data for the per-champion SEO pages added 2026-11-28: lane pages
 * (/champions/<slug>/<lane>), the runes page (/champions/<slug>/runes) and
 * the FAQ on every champion page.
 *
 * Why these pages exist: a competitor two months old outranked the site with
 * ~20x the pages -- one per champion AND lane, plus counters and runes pages,
 * each answering one search ("ahri mid build", "ahri runes wild rift"). One
 * page per champion has to compete for all of those with a single URL.
 *
 * The rule that keeps them from being thin template pages: every page shows
 * numbers no other page on the site shows. A lane page exists only when that
 * lane has its own measured item cores or rune pages; the runes page only
 * when there is measured rune data. Same guardrails as the advisor
 * (web/advisor/prompt.py): item tabs under 3 rows are a near-empty page
 * (Ahri mid showed 2 bruiser cores on a mage), and a tab the source stopped
 * refreshing is labelled, not presented as current.
 */
import ladderBuilds from "@/data/ladder_builds.json";
import ladderBuildsNa from "@/data/ladder_builds_na.json";
import engineData from "@/data/engine.json";
import itemsCatalogue from "@/data/items.json";
import { getChampionLoadouts, type ChampionLoadoutLane, type LoadoutRow, type LoadoutTab } from "@/lib/cn-loadouts";
import type { Champion } from "@/lib/data";
import { getMatchups, hasCounterPage } from "@/lib/counters";
import { getT } from "@/lib/ui-i18n";
import { displayName, hasLocale, itemName as localItem, runeName as localRune, spellName as localSpell } from "@/lib/i18n";
import { getChampionDetails } from "@/lib/champion-details";
import { getChampionHistory } from "@/lib/champion-history";

export const LANES = ["baron", "jungle", "mid", "dragon", "support"] as const;
export type Lane = (typeof LANES)[number];
export const LANE_LABEL: Record<Lane, string> = {
  baron: "Baron Lane", jungle: "Jungle", mid: "Mid Lane", dragon: "Dragon Lane", support: "Support",
};

/** Minimum item-core rows for a lane's items to count as measured. */
const MIN_ITEM_ROWS = 3;
/** Rows under this pick rate are noise in the source and never shown. */
const MIN_PICK = 1.5;

export function usableRows(tab: LoadoutTab | undefined, kind: "items" | "runes" | "spells" | "boots" | "versus"): LoadoutRow[] {
  if (!tab) return [];
  if (tab.stale && kind !== "boots") return [];
  const rows = tab.rows ?? [];
  if (kind === "items" && rows.length < MIN_ITEM_ROWS) return [];
  const minPick = kind === "versus" ? 1 : MIN_PICK;
  return rows.filter((r) => (r.pickRate ?? 0) >= minPick).sort((a, b) => (b.pickRate ?? 0) - (a.pickRate ?? 0));
}

/** The champion's lanes with enough measured data for their own page. */
export function lanePages(slug: string): ChampionLoadoutLane[] {
  return getChampionLoadouts(slug).filter((lane) =>
    (LANES as readonly string[]).includes(lane.lane)
    && (usableRows(lane.tabs.items, "items").length > 0 || usableRows(lane.tabs.runes, "runes").length > 0));
}

export function laneFor(slug: string, lane: string): ChampionLoadoutLane | null {
  return lanePages(slug).find((l) => l.lane === lane) ?? null;
}

type LadderRecord = {
  items?: { slug: string; count: number; of: number }[];
  keystones?: { name: string; count: number }[];
  minors?: { name: string; count: number }[];
};

/** EU + NA top-player rune counts, merged. */
export function ladderRunes(name: string): { keystones: { name: string; count: number }[]; minors: { name: string; count: number }[]; players: number } {
  const recs = [(ladderBuilds as Record<string, LadderRecord>)[name], (ladderBuildsNa as Record<string, LadderRecord>)[name]].filter(Boolean) as LadderRecord[];
  const merge = (key: "keystones" | "minors") => {
    const total = new Map<string, number>();
    for (const rec of recs) for (const r of rec[key] ?? []) total.set(r.name, (total.get(r.name) ?? 0) + r.count);
    return [...total.entries()].map(([n, count]) => ({ name: n, count })).sort((a, b) => b.count - a.count);
  };
  const players = recs.reduce((sum, rec) => sum + (rec.items?.[0]?.of ?? 0), 0);
  return { keystones: merge("keystones"), minors: merge("minors"), players };
}

type RuneInfo = { slug: string; icon?: string; tree?: string; type?: string; description?: string };
const RUNES = new Map(Object.entries((engineData as unknown as { runes: Record<string, RuneInfo> }).runes));
export function runeInfo(name: string): RuneInfo | undefined {
  return RUNES.get(name);
}

const ITEM_NAMES = new Map((itemsCatalogue as { slug: string; name: string; category?: string }[]).map((i) => [i.slug, i]));

/** The non-boots items top EU + NA players build most, most-built first. */
export function ladderTopItems(name: string): string[] {
  const recs = [(ladderBuilds as Record<string, LadderRecord>)[name], (ladderBuildsNa as Record<string, LadderRecord>)[name]].filter(Boolean) as LadderRecord[];
  const total = new Map<string, number>();
  for (const rec of recs) for (const i of rec.items ?? []) total.set(i.slug, (total.get(i.slug) ?? 0) + i.count);
  return [...total.entries()]
    .filter(([slug]) => ITEM_NAMES.get(slug) && ITEM_NAMES.get(slug)?.category !== "Boots")
    .sort((a, b) => b[1] - a[1])
    .map(([slug]) => ITEM_NAMES.get(slug)!.name);
}

export function hasRunesPage(champion: Champion): boolean {
  const ladder = ladderRunes(champion.name);
  if (ladder.keystones.length > 0) return true;
  return getChampionLoadouts(champion.slug).some((lane) => usableRows(lane.tabs.runes, "runes").length > 0);
}

export type Faq = { q: string; a: string }[];

const pct = (n: number) => `${n.toFixed(1)}%`;

/** FAQ for the champion page, answered from the same data the page shows. */
export function championFaq(champion: Champion, opts: { tierLabel: string; topItems?: string[]; lang?: string }): Faq {
  // Every Q and A is a t() template (lib/ui-i18n.ts), so the FAQ reads
  // naturally in each language; names come from the localized-names table.
  const lang = opts.lang ?? "en";
  const t = getT(lang);
  const faq: Faq = [];
  const name = displayName(champion.name, lang);
  const item = (n: string) => (hasLocale(lang) ? localItem(n, lang) : n);
  const rune = (n: string) => (hasLocale(lang) ? localRune(n, lang) : n);
  const champ = (n: string) => displayName(n, lang);
  const topItems = opts.topItems ?? ladderTopItems(champion.name);
  if (topItems.length >= 3) {
    faq.push({
      q: t("What is the best {name} build in Wild Rift?", { name }),
      a: t("The items {name}'s top players build most are {items}. Build Studio can generate a build for your own playstyle and matchup.", { name, items: topItems.slice(0, 5).map(item).join(", ") }),
    });
  }
  const { weak, strong } = getMatchups(champion.slug);
  if (weak.length > 0) {
    faq.push({
      q: t("Who counters {name} in Wild Rift?", { name }),
      a: t("{list} are {name}'s hardest matchups in China Legendary ranked.", { name, list: weak.slice(0, 3).map((m) => t("{champ} ({name} wins {wr})", { champ: champ(m.champion.name), name, wr: pct(m.winRate) })).join(", ") }),
    });
  }
  if (strong.length > 0) {
    faq.push({
      q: t("Who is {name} good against?", { name }),
      a: t("{name} does best against {list}.", { name, list: strong.slice(0, 3).map((m) => `${champ(m.champion.name)} (${pct(m.winRate)})`).join(", ") }),
    });
  }
  const runes = ladderRunes(champion.name);
  if (runes.keystones.length > 0 && runes.players > 0) {
    const k = runes.keystones[0];
    faq.push({
      q: t("What are the best runes for {name}?", { name }),
      a: runes.minors.length
        ? t("{keystone} is the keystone {count} of {players} top {name} players run, most often with {minors}.", { keystone: rune(k.name), count: k.count, players: runes.players, name, minors: runes.minors.slice(0, 3).map((m) => rune(m.name)).join(", ") })
        : t("{keystone} is the keystone {count} of {players} top {name} players run.", { keystone: rune(k.name), count: k.count, players: runes.players, name }),
    });
  }
  // Summoner spells: the most-played pair in China Legendary, any lane.
  const spellRow = getChampionLoadouts(champion.slug)
    .flatMap((l) => usableRows(l.tabs.spells, "spells"))
    .sort((a, b) => b.pickRate - a.pickRate)[0];
  if (spellRow) {
    faq.push({
      q: t("What summoner spells does {name} take?", { name }),
      a: t("{spells}, picked in {pick} of {name}'s China Legendary games.", { spells: spellRow.entities.map((e) => (hasLocale(lang) ? localSpell(e.name, lang) : e.name)).join(" + "), pick: pct(spellRow.pickRate), name }),
    });
  }
  const skill = getChampionDetails(champion.slug)?.skillPriority ?? [];
  if (skill.length >= 2) {
    faq.push({
      q: t("What is {name}'s skill order?", { name }),
      a: t("Max {order}, taking the ultimate whenever it is available.", { order: skill.join(" > ") }),
    });
  }
  faq.push({
    q: t("Is {name} good in Wild Rift right now?", { name }),
    a: t("{name} is {tier} with a {wr} win rate across its best players in EU and NA.", { name, tier: opts.tierLabel, wr: pct(champion.wr) }),
  });
  if (champion.difficultyLabel) {
    faq.push({
      q: t("Is {name} hard to play?", { name }),
      a: t("{name}'s difficulty is {difficulty}.", { name, difficulty: t(champion.difficultyLabel) }),
    });
  }
  const lastChange = getChampionHistory(champion.name).changes.find((c) => !c.modeOnly);
  if (lastChange) {
    faq.push({
      q: t("When was {name} last changed?", { name }),
      a: t("{name} was last changed in patch {patch}.", { name, patch: lastChange.patch }),
    });
  }
  const best = (champion.globalBestPlayerPodium ?? champion.bestPlayerPodium)?.players?.[0];
  if (best?.player) {
    faq.push({
      q: t("Who is the best {name} player?", { name }),
      a: best.server
        ? t("{player} ({server}) tops the {name} ranking this season, combining win rate, ladder strength and games played.", { player: best.player, server: best.server, name })
        : t("{player} tops the {name} ranking this season, combining win rate, ladder strength and games played.", { player: best.player, name }),
    });
  }
  const lanes = lanePages(champion.slug);
  if (lanes.length > 1) {
    faq.push({
      q: t("What lane is {name} played in?", { name }),
      a: t("{name} is played in {lanes}. Each lane has its own build and matchups.", { name, lanes: lanes.map((l) => t(LANE_LABEL[l.lane as Lane])).join(", ") }),
    });
  }
  return faq;
}

export function faqJsonLd(faq: Faq) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faq.map(({ q, a }) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })),
  };
}

/** Every SEO subpage a champion has, for cross-linking and the sitemap. */
export function championSubpages(champion: Champion): { href: string; label: string }[] {
  const links: { href: string; label: string }[] = [];
  for (const lane of lanePages(champion.slug)) {
    links.push({ href: `/champions/${champion.slug}/${lane.lane}`, label: `${champion.name} ${LANE_LABEL[lane.lane as Lane]}` });
  }
  if (hasRunesPage(champion)) links.push({ href: `/champions/${champion.slug}/runes`, label: `${champion.name} runes` });
  if (hasCounterPage(champion.slug)) links.push({ href: `/champions/${champion.slug}/counters`, label: `How to counter ${champion.name}` });
  return links;
}
