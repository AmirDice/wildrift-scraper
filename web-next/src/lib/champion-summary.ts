/**
 * "{Champion} at a glance": the paragraph at the top of a champion page.
 *
 * Every sentence is computed from this champion's own data -- its place on the
 * Global list, how its top players do in each region, where the three servers'
 * builds agree and where they split, its latest patch change and its sharpest
 * matchups. AdSense rejected the site for low-value content, and part of the
 * reason was that 143 champion pages shared most of their prose: the same UI
 * explanations with the name swapped. This is the part of each page that is
 * only true of that champion. A sentence with nothing to say is left out
 * rather than filled with filler.
 */
import itemsCatalogue from "@/data/items.json";
import { getGlobalChampions } from "@/lib/cn";
import { getChampionHistory } from "@/lib/champion-history";
import { getMatchups } from "@/lib/counters";
import { getChampion, regionBoard, tierLabel } from "@/lib/data";
import { buildsByServer } from "@/lib/ladder-build";
import { WINRATE_PATCH } from "@/lib/announcement";
import { CURRENT_PATCH } from "@/lib/patch";
import { getT, type TFunction } from "@/lib/ui-i18n";
import { displayName, itemName as localItem, runeName as localRune, hasLocale } from "@/lib/i18n";

const ITEM_NAMES = new Map(
  (itemsCatalogue as { slug: string; name: string }[]).map((item) => [item.slug, item.name]),
);
/** Language context for one summary: t() for sentences, local names. */
type Ctx = { t: TFunction; lang: string };
const itemName = (slug: string, ctx?: Ctx) => {
  const name = ITEM_NAMES.get(slug) ?? slug;
  return ctx && hasLocale(ctx.lang) ? localItem(name, ctx.lang) : name;
};
const keystoneName = (name: string, ctx: Ctx) => (hasLocale(ctx.lang) ? localRune(name, ctx.lang) : name);
const pct = (value: number) => `${value.toFixed(1)}%`;
const REGION_NAME: Record<string, string> = { eu: "EU", na: "NA", cn: "China" };

function list(names: string[], ctx?: Ctx): string {
  if (names.length <= 1) return names.join("");
  const head = names.slice(0, -1).join(", ");
  const last = names[names.length - 1];
  return ctx ? ctx.t("{a} and {b}", { a: head, b: last }) : `${head} and ${last}`;
}

function ordinal(n: number): string {
  const tail = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${tail}`;
}

/** Where the champion stands, overall and per region. */
function standing(slug: string, name: string, ctx: Ctx): string | null {
  const pool = getGlobalChampions()
    .filter((c) => !c.statsPending && Number.isFinite(c.wr))
    .sort((a, b) => b.wr - a.wr);
  const index = pool.findIndex((c) => c.slug === slug);
  if (index < 0) return null;
  const entry = pool[index];
  const rolePool = pool.filter((c) => c.role === entry.role);
  const roleIndex = rolePool.findIndex((c) => c.slug === slug);
  let text = ctx.lang === "en"
    ? `${name} is ${tierLabel(entry.tier)} tier on the Global list at ${pct(entry.wr)}, `
      + `${ordinal(index + 1)} of ${pool.length} champions and ${ordinal(roleIndex + 1)} of ${rolePool.length} ${entry.role} champions.`
    : ctx.t("{name} is {tier} tier on the Global list at {wr}, #{rank} of {total} champions and #{roleRank} of {roleTotal} {role} champions.",
      { name, tier: tierLabel(entry.tier), wr: pct(entry.wr), rank: index + 1, total: pool.length, roleRank: roleIndex + 1, roleTotal: rolePool.length, role: ctx.t(entry.role) });

  const regions = (["EU", "NA"] as const)
    .map((region) => ({ region, wr: regionBoard(region).champions.find((c) => c.slug === slug)?.wr }))
    .filter((row): row is { region: "EU" | "NA"; wr: number } => Number.isFinite(row.wr));
  if (regions.length >= 2) {
    const sorted = [...regions].sort((a, b) => b.wr - a.wr);
    const best = sorted[0], worst = sorted[sorted.length - 1];
    const label = (region: string) => region;
    text += best.wr - worst.wr >= 1
      ? " " + ctx.t("Its top players do best in {best} ({bestWr}) and worst in {worst} ({worstWr}), a gap of {gap} points.",
          { best: label(best.region), bestWr: pct(best.wr), worst: label(worst.region), worstWr: pct(worst.wr), gap: (best.wr - worst.wr).toFixed(1) })
      : " " + ctx.t("Its top players post close results in every region: {list}.", { list: list(sorted.map((row) => `${label(row.region)} ${pct(row.wr)}`), ctx) });
  }
  return text;
}

/** Where the EU and NA top players build the same, and where they split. */
function builds(name: string, ctx: Ctx): string | null {
  const byServer = buildsByServer(name);
  const servers = (["eu", "na"] as const).filter((server) => byServer[server]?.items?.length);
  if (!servers.length) return null;
  const sets = servers.map((server) => new Set(byServer[server]!.items));
  const shared = byServer[servers[0]]!.items.filter((slug) => sets.every((set) => set.has(slug)));
  const parts: string[] = [];
  if (servers.length >= 2 && shared.length) {
    parts.push(ctx.t("Top players in {regions} all build {items}.", { regions: list(servers.map((s) => ctx.t(REGION_NAME[s])), ctx), items: list(shared.slice(0, 3).map((x) => itemName(x, ctx)), ctx) }));
  } else if (servers.length === 1) {
    parts.push(ctx.t("Its {region} top players build {items}.", { region: ctx.t(REGION_NAME[servers[0]]), items: list(byServer[servers[0]]!.items.slice(0, 3).map((x) => itemName(x, ctx)), ctx) }));
  }
  // The single clearest regional difference: an item one server's ladder
  // builds that is missing from every other server's top five.
  let distinct: { server: string; slug: string; rate: number } | null = null;
  for (const [i, server] of servers.entries()) {
    const build = byServer[server]!;
    for (const slug of build.items) {
      if (sets.every((set, j) => j === i || !set.has(slug))) {
        const rate = build.itemRates?.[slug] ?? 0;
        if (!distinct || rate > distinct.rate) distinct = { server, slug, rate };
      }
    }
  }
  if (distinct && servers.length >= 2) {
    parts.push(distinct.rate
      ? ctx.t("{region} stands apart with {item}, built by {rate}% of its top players, which the other servers' top builds leave out.", { region: ctx.t(REGION_NAME[distinct.server]), item: itemName(distinct.slug, ctx), rate: Math.round(distinct.rate) })
      : ctx.t("{region} stands apart with {item}, which the other servers' top builds leave out.", { region: ctx.t(REGION_NAME[distinct.server]), item: itemName(distinct.slug, ctx) }));
  }
  const keystones = servers
    .map((server) => ({ server, keystone: byServer[server]!.runes?.keystone }))
    .filter((row): row is { server: "eu" | "na"; keystone: string } => Boolean(row.keystone));
  const distinctKeystones = [...new Set(keystones.map((row) => row.keystone))];
  if (distinctKeystones.length === 1 && keystones.length >= 2) {
    parts.push(ctx.t("{keystone} is the keystone on every server.", { keystone: keystoneName(distinctKeystones[0], ctx) }));
  } else if (distinctKeystones.length > 1) {
    const groups = distinctKeystones.map((keystone) =>
      ctx.t("{keystone} in {regions}", { keystone: keystoneName(keystone, ctx), regions: list(keystones.filter((row) => row.keystone === keystone).map((row) => ctx.t(REGION_NAME[row.server])), ctx) }));
    parts.push(ctx.t("The keystone splits: {groups}.", { groups: groups.join(", ") }));
  }
  return parts.length ? parts.join(" ") : null;
}

/** The latest balance change, and whether the win rates above predate it. */
function latestChange(name: string, display: string, ctx: Ctx): string | null {
  const change = getChampionHistory(name).changes.find((c) => !c.modeOnly);
  if (!change) return null;
  const date = new Date(change.publishedAt);
  const when = Number.isFinite(date.getTime())
    ? ` (${date.toLocaleDateString(ctx.lang === "en" ? "en-US" : ctx.lang === "zh" ? "zh-CN" : ctx.lang, { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" })})`
    : "";
  // "Patch notes" is the history's placeholder for a change with no named
  // ability; it is not something a reader can look up.
  const touched = [...new Set(change.changes.map((row) => row.ability)
    .filter((ability) => ability && !/^patch notes$/i.test(ability)))];
  let text = touched.length
    ? ctx.t("{name} was last changed in patch {patch}{when}, to {list}.", { name: display, patch: change.patch, when,
        list: list(touched.slice(0, 3), ctx) + (touched.length > 3 ? " " + ctx.t("and {n} more", { n: touched.length - 3 }) : "") })
    : ctx.t("{name} was last changed in patch {patch}{when}.", { name: display, patch: change.patch, when });
  if (change.patch === CURRENT_PATCH && WINRATE_PATCH && WINRATE_PATCH !== CURRENT_PATCH) {
    text += " " + ctx.t("The win rates above were collected on {patch}, before that change.", { patch: WINRATE_PATCH });
  }
  return text;
}

/** The sharpest matchups the matchup data records. */
function matchups(slug: string, name: string, ctx: Ctx): string | null {
  const { strong, weak } = getMatchups(slug);
  // Already sorted strongest edge first, measured in China.
  const top = (rows: typeof strong) => rows.slice(0, 2)
    .map((row) => `${displayName(row.champion.name, ctx.lang)} (${row.winRate.toFixed(1)}%)`);
  const good = top(strong), bad = top(weak);
  if (!good.length && !bad.length) return null;
  if (good.length && bad.length) return ctx.t("In China, {name}'s best matchups are {good}; the hardest are {bad}.", { name, good: list(good, ctx), bad: list(bad, ctx) });
  return good.length
    ? ctx.t("In China, {name}'s best matchups are {good}.", { name, good: list(good, ctx) })
    : ctx.t("In China, {name}'s hardest matchups are {bad}.", { name, bad: list(bad, ctx) });
}

export function championSummary(slug: string, lang = "en"): string[] {
  const champion = getChampion(slug);
  if (!champion || champion.statsPending) return [];
  // Each sentence is one t() template, so word order is the target
  // language's; names come from the localized-names table.
  const ctx: Ctx = { t: getT(lang), lang };
  const name = displayName(champion.name, lang);
  return [
    standing(champion.slug, name, ctx),
    builds(champion.name, ctx),
    latestChange(champion.name, name, ctx),
    matchups(champion.slug, name, ctx),
  ].filter((paragraph): paragraph is string => Boolean(paragraph));
}
