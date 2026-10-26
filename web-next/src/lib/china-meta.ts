import loadoutData from "@/data/cn_loadouts.json";
import itemsData from "@/data/items.json";
import runeIconsData from "@/data/rune_icons.json";
import spellsData from "@/data/spells.json";
import siteData from "@/data/site.json";
import historyData from "@/data/champion_change_history.json";
import { bestDuos, partnerQueues } from "@/lib/cn-partners";

/**
 * "China this week" on the meta page: what the CN Legendary loadout captures
 * say across the whole roster, built from each lane's pooled week
 * (scripts/export_loadouts_for_web.py attach_week_and_trend).
 *
 * Every figure is a SHARE of a champion-lane's games, never a game count:
 * China's app gives none. So an item's "presence" is the share of a lane's
 * games whose three-item core contains it, and roster-wide numbers average
 * lanes, each lane counting once whatever its champion's popularity.
 */
type Row = { entities: string[]; winRate: number; pickRate: number; seen?: number; trend?: [string, number, number][] };
type Tab = { date?: string | null; rows: Row[]; week?: { captures: number; from: string; to: string; rows: Row[] } };
type Lane = { lane: string; capturedAt: string; tabs: Record<"items" | "runes" | "boots" | "spells" | "versus", Tab> };
type Data = { champions: Record<string, Lane[]> };

const DATA = loadoutData as unknown as Data;
const CHAMPS = new Map((siteData.champions as { slug: string; name: string; icon: string; role: string }[]).map((c) => [c.slug, c]));
const ITEMS = new Map((itemsData as { name: string; slug: string; icon: string }[]).map((item) => [item.name, item]));
const RUNES = runeIconsData as Record<string, string>;
const SPELLS = new Map((spellsData as { name: string; icon: string }[]).map((spell) => [spell.name, spell]));

export const LANES = ["baron", "jungle", "mid", "dragon", "support"] as const;
export type Lane5 = (typeof LANES)[number];
export const LANE_NAME: Record<Lane5, string> = { baron: "Baron", jungle: "Jungle", mid: "Mid", dragon: "Dragon", support: "Support" };

const weekRows = (tab: Tab | undefined) => (tab?.week && tab.week.captures > 1 ? tab.week.rows : tab?.rows) ?? [];
const r1 = (v: number) => Math.round(v * 10) / 10;

export type Ranked = { name: string; icon: string; href?: string; lanes: number; presence: number; winRate: number };

/** Items or keystones by how much of the roster's games they appear in. */
function aggregate(kind: "items" | "runes", lane: Lane5 | "all"): Ranked[] {
  const acc = new Map<string, { lanes: number; presence: number; wr: number; weight: number }>();
  let laneCount = 0;
  for (const lanes of Object.values(DATA.champions)) {
    for (const record of lanes) {
      if (lane !== "all" && record.lane !== lane) continue;
      const rows = weekRows(record.tabs[kind]);
      if (!rows.length) continue;
      laneCount += 1;
      const here = new Map<string, { share: number; wr: number }>();
      for (const row of rows) {
        // A core counts each of its items; a rune page counts its keystone.
        const names = kind === "items" ? row.entities : row.entities.slice(0, 1);
        for (const name of new Set(names)) {
          const cur = here.get(name) ?? { share: 0, wr: 0 };
          cur.share += row.pickRate;
          cur.wr += row.winRate * row.pickRate;
          here.set(name, cur);
        }
      }
      for (const [name, { share, wr }] of here) {
        const cur = acc.get(name) ?? { lanes: 0, presence: 0, wr: 0, weight: 0 };
        cur.lanes += share >= 20 ? 1 : 0;
        cur.presence += Math.min(share, 100);
        cur.wr += wr;
        cur.weight += share;
        acc.set(name, cur);
      }
    }
  }
  return [...acc.entries()]
    .map(([name, v]) => ({
      name,
      icon: kind === "items" ? ITEMS.get(name)?.icon ?? "/items/unknown.webp" : RUNES[name] ?? "/items/unknown.webp",
      href: kind === "items" ? (ITEMS.get(name) ? `/items#${ITEMS.get(name)!.slug}` : undefined) : "/runes",
      lanes: v.lanes,
      presence: laneCount ? r1(v.presence / laneCount) : 0,
      winRate: v.weight ? r1(v.wr / v.weight) : 0,
    }))
    .filter((row) => row.presence > 0)
    .sort((a, b) => b.presence - a.presence)
    .slice(0, 15);
}

export type Rising = {
  champion: string; slug: string; icon: string; lane: string;
  kind: "items" | "runes"; entities: { name: string; icon: string }[];
  from: number; to: number; since: string; winRate: number;
};

/**
 * Cores and rune pages players are switching TO: played at least 3% of the
 * lane's games this week, and at least double (and 2 points over) their share
 * in the lane's first archived capture. Gated like the panel's pick-rate
 * arrows, because a 0.5% -> 1.2% row is noise, not a trend.
 */
function rising(): Rising[] {
  const out: Rising[] = [];
  for (const [slug, lanes] of Object.entries(DATA.champions)) {
    const champ = CHAMPS.get(slug);
    if (!champ) continue;
    for (const record of lanes) {
      for (const kind of ["items", "runes"] as const) {
        const tab = record.tabs[kind];
        if (!tab?.week || tab.week.captures < 2) continue;
        for (const row of tab.week.rows) {
          const first = row.trend?.[0];
          const last = row.trend?.[row.trend.length - 1];
          if (!first || !last || first === last || row.pickRate < 3) continue;
          if (last[2] < 3 || last[2] < first[2] * 2 || last[2] - first[2] < 2) continue;
          out.push({
            champion: champ.name, slug, icon: champ.icon, lane: record.lane, kind,
            entities: row.entities.map((name) => ({ name, icon: kind === "items" ? ITEMS.get(name)?.icon ?? "/items/unknown.webp" : RUNES[name] ?? "/items/unknown.webp" })),
            from: first[2], to: last[2], since: first[0], winRate: r1(row.winRate),
          });
        }
      }
    }
  }
  return out.sort((a, b) => (b.to - b.from) - (a.to - a.from)).slice(0, 12);
}

export type SpellPair = { pair: string; icons: string[]; share: number; winRate: number };

function spellsByLane(): Record<Lane5, SpellPair[]> {
  const out = {} as Record<Lane5, SpellPair[]>;
  for (const lane of LANES) {
    const acc = new Map<string, { share: number; wr: number; names: string[] }>();
    let n = 0;
    for (const lanes of Object.values(DATA.champions)) {
      for (const record of lanes) {
        if (record.lane !== lane) continue;
        const rows = weekRows(record.tabs.spells);
        if (!rows.length) continue;
        n += 1;
        for (const row of rows) {
          const names = [...row.entities].sort();
          const key = names.join(" + ");
          const cur = acc.get(key) ?? { share: 0, wr: 0, names };
          cur.share += row.pickRate;
          cur.wr += row.winRate * row.pickRate;
          acc.set(key, cur);
        }
      }
    }
    out[lane] = [...acc.entries()]
      .map(([pair, v]) => ({ pair, icons: v.names.map((name) => SPELLS.get(name)?.icon ?? "/items/unknown.webp"), share: n ? r1(v.share / n) : 0, winRate: v.share ? r1(v.wr / v.share) : 0 }))
      .sort((a, b) => b.share - a.share)
      .slice(0, 5);
  }
  return out;
}

export type PatchShift = {
  champion: string; slug: string; icon: string; lane: string;
  gained: { entities: string[]; from: number; to: number } | null;
  lost: { entities: string[]; from: number; to: number } | null;
};

/**
 * What a patch did to China's builds for the champions it changed: per lane,
 * the core that gained the most share since the last capture before the
 * patch, and the one that lost the most. Uses the row trends, so it needs a
 * capture from before the patch went live.
 */
function patchShifts(patch: string): { patch: string; before: string; shifts: PatchShift[] } | null {
  const history = historyData as { champions: Record<string, { patch: string; publishedAt: string; modeOnly: boolean }[]> };
  let published = "";
  const changed = new Set<string>();
  for (const [name, changes] of Object.entries(history.champions)) {
    for (const change of changes) {
      if (change.patch === patch && !change.modeOnly) {
        changed.add(name);
        published = change.publishedAt.slice(5, 10);
      }
    }
  }
  if (!changed.size) return null;
  const shifts: PatchShift[] = [];
  let before = "";
  for (const [slug, lanes] of Object.entries(DATA.champions)) {
    const champ = CHAMPS.get(slug);
    if (!champ || !changed.has(champ.name)) continue;
    for (const record of lanes) {
      const rows = record.tabs.items?.week?.rows ?? [];
      const pre = (row: Row) => [...(row.trend ?? [])].reverse().find(([d]) => d < published);
      const post = (row: Row) => row.trend?.[row.trend.length - 1];
      const moves = rows
        .map((row) => ({ row, a: pre(row), b: post(row) }))
        .filter((m) => m.a && m.b && m.b[0] >= published)
        .map((m) => ({ entities: m.row.entities, from: m.a![2], to: m.b![2], since: m.a![0] }));
      if (!moves.length) continue;
      before = before || moves[0].since;
      const up = [...moves].sort((x, y) => (y.to - y.from) - (x.to - x.from))[0];
      const down = [...moves].sort((x, y) => (x.to - x.from) - (y.to - y.from))[0];
      shifts.push({
        champion: champ.name, slug, icon: champ.icon, lane: record.lane,
        gained: up && up.to - up.from >= 2 ? up : null,
        lost: down && down.from - down.to >= 2 ? down : null,
      });
    }
  }
  return shifts.length ? { patch, before, shifts: shifts.filter((s) => s.gained || s.lost) } : null;
}

export function chinaThisWeek(patch: string) {
  const items: Record<string, Ranked[]> = { all: aggregate("items", "all") };
  const keystones: Record<string, Ranked[]> = { all: aggregate("runes", "all") };
  for (const lane of LANES) {
    items[lane] = aggregate("items", lane);
    keystones[lane] = aggregate("runes", lane);
  }
  const anyWeek = Object.values(DATA.champions).flat().find((lane) => lane.tabs.items?.week)?.tabs.items.week;
  return {
    window: anyWeek ? { from: anyWeek.from, to: anyWeek.to, captures: anyWeek.captures } : null,
    rising: rising(),
    items,
    keystones,
    spells: spellsByLane(),
    duos: partnerQueues().map((q) => ({ ...q, groups: bestDuos(q.id, 6) })).filter((q) => q.groups.length),
    patch: patchShifts(patch),
  };
}

export type ChinaThisWeek = ReturnType<typeof chinaThisWeek>;
