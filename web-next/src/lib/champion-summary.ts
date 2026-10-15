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

const ITEM_NAMES = new Map(
  (itemsCatalogue as { slug: string; name: string }[]).map((item) => [item.slug, item.name]),
);
const itemName = (slug: string) => ITEM_NAMES.get(slug) ?? slug;
const pct = (value: number) => `${value.toFixed(1)}%`;
const REGION_NAME: Record<string, string> = { eu: "EU", na: "NA", cn: "China" };

function list(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

function ordinal(n: number): string {
  const tail = n % 100 >= 11 && n % 100 <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${tail}`;
}

/** Where the champion stands, overall and per region. */
function standing(slug: string, name: string): string | null {
  const pool = getGlobalChampions()
    .filter((c) => !c.statsPending && Number.isFinite(c.wr))
    .sort((a, b) => b.wr - a.wr);
  const index = pool.findIndex((c) => c.slug === slug);
  if (index < 0) return null;
  const entry = pool[index];
  const rolePool = pool.filter((c) => c.role === entry.role);
  const roleIndex = rolePool.findIndex((c) => c.slug === slug);
  let text = `${name} is ${tierLabel(entry.tier)} tier on the Global list at ${pct(entry.wr)}, `
    + `${ordinal(index + 1)} of ${pool.length} champions and ${ordinal(roleIndex + 1)} of ${rolePool.length} ${entry.role} champions.`;

  const regions = (["EU", "NA", "CN"] as const)
    .map((region) => ({ region, wr: regionBoard(region).champions.find((c) => c.slug === slug)?.wr }))
    .filter((row): row is { region: "EU" | "NA" | "CN"; wr: number } => Number.isFinite(row.wr));
  if (regions.length >= 2) {
    const sorted = [...regions].sort((a, b) => b.wr - a.wr);
    const best = sorted[0], worst = sorted[sorted.length - 1];
    const label = (region: string) => (region === "CN" ? "China" : region);
    text += best.wr - worst.wr >= 1
      ? ` Its top players do best in ${label(best.region)} (${pct(best.wr)}) and worst in ${label(worst.region)} (${pct(worst.wr)}), a gap of ${(best.wr - worst.wr).toFixed(1)} points.`
      : ` Its top players post close results in every region: ${list(sorted.map((row) => `${label(row.region)} ${pct(row.wr)}`))}.`;
  }
  return text;
}

/** Where the three servers' top players build the same, and where they split. */
function builds(name: string): string | null {
  const byServer = buildsByServer(name);
  const servers = (["eu", "na", "cn"] as const).filter((server) => byServer[server]?.items?.length);
  if (!servers.length) return null;
  const sets = servers.map((server) => new Set(byServer[server]!.items));
  const shared = byServer[servers[0]]!.items.filter((slug) => sets.every((set) => set.has(slug)));
  const parts: string[] = [];
  if (servers.length >= 2 && shared.length) {
    parts.push(`Top players in ${list(servers.map((s) => REGION_NAME[s]))} all build ${list(shared.slice(0, 3).map(itemName))}.`);
  } else if (servers.length === 1) {
    parts.push(`Its ${REGION_NAME[servers[0]]} top players build ${list(byServer[servers[0]]!.items.slice(0, 3).map(itemName))}.`);
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
    parts.push(`${REGION_NAME[distinct.server]} stands apart with ${itemName(distinct.slug)}`
      + (distinct.rate ? `, built by ${Math.round(distinct.rate)}% of its top players,` : "")
      + " which the other servers' top builds leave out.");
  }
  const keystones = servers
    .map((server) => ({ server, keystone: byServer[server]!.runes?.keystone }))
    .filter((row): row is { server: "eu" | "na" | "cn"; keystone: string } => Boolean(row.keystone));
  const distinctKeystones = [...new Set(keystones.map((row) => row.keystone))];
  if (distinctKeystones.length === 1 && keystones.length >= 2) {
    parts.push(`${distinctKeystones[0]} is the keystone on every server.`);
  } else if (distinctKeystones.length > 1) {
    const groups = distinctKeystones.map((keystone) =>
      `${keystone} in ${list(keystones.filter((row) => row.keystone === keystone).map((row) => REGION_NAME[row.server]))}`);
    parts.push(`The keystone splits: ${groups.join(", ")}.`);
  }
  return parts.length ? parts.join(" ") : null;
}

/** The latest balance change, and whether the win rates above predate it. */
function latestChange(name: string): string | null {
  const change = getChampionHistory(name).changes.find((c) => !c.modeOnly);
  if (!change) return null;
  const date = new Date(change.publishedAt);
  const when = Number.isFinite(date.getTime())
    ? ` (${date.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" })})`
    : "";
  // "Patch notes" is the history's placeholder for a change with no named
  // ability; it is not something a reader can look up.
  const touched = [...new Set(change.changes.map((row) => row.ability)
    .filter((ability) => ability && !/^patch notes$/i.test(ability)))];
  let text = `${name} was last changed in patch ${change.patch}${when}`
    // Names what changed rather than quoting Riot's summary: a quoted patch
    // note is the same sentence on this site and on Riot's, which is the
    // duplicate text this paragraph exists to replace.
    + (touched.length ? `, to ${list(touched.slice(0, 3))}${touched.length > 3 ? ` and ${touched.length - 3} more` : ""}.` : ".");
  if (change.patch === CURRENT_PATCH && WINRATE_PATCH && WINRATE_PATCH !== CURRENT_PATCH) {
    text += ` The win rates above were collected on ${WINRATE_PATCH}, before that change.`;
  }
  return text;
}

/** The sharpest matchups the matchup data records. */
function matchups(slug: string, name: string): string | null {
  const { strong, weak } = getMatchups(slug);
  const top = (rows: typeof strong) => [...rows]
    .sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0))
    .slice(0, 2)
    .map((row) => row.champion.name);
  const good = top(strong), bad = top(weak);
  if (!good.length && !bad.length) return null;
  if (good.length && bad.length) return `${name}'s best matchups are ${list(good)}; the hardest are ${list(bad)}.`;
  return good.length ? `${name}'s best matchups are ${list(good)}.` : `${name}'s hardest matchups are ${list(bad)}.`;
}

export function championSummary(slug: string): string[] {
  const champion = getChampion(slug);
  if (!champion || champion.statsPending) return [];
  return [
    standing(champion.slug, champion.name),
    builds(champion.name),
    latestChange(champion.name),
    matchups(champion.slug, champion.name),
  ].filter((paragraph): paragraph is string => Boolean(paragraph));
}
