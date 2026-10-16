import comboData from "@/data/champion_combos.json";
import engineData from "@/data/engine.json";
import itemsData from "@/data/items.json";
import { CHANGELOG, WINRATE_PATCH } from "@/lib/announcement";
import { getChampion, getChampions, pendingChampions, regionBoard, tierLabel, type Champion } from "@/lib/data";
import { getGlobalBySlug, getGlobalChampions } from "@/lib/cn";
import { getChampionDetails } from "@/lib/champion-details";
import { getChampionHistory } from "@/lib/champion-history";
import { getChampionLoadouts, type LoadoutTab } from "@/lib/cn-loadouts";
import { getMatchups } from "@/lib/counters";
import { ITEM_ALIASES } from "@/lib/item-search";
import { MOVERS_META, moverBySlug } from "@/lib/movers";
import { buildsByServer } from "@/lib/ladder-build";
import { CURRENT_PATCH } from "@/lib/patch";
import type { AgentAnswer } from "@/lib/agent-types";

/*
 * The site agent answers in two ways, and the split matters more than it looks.
 *
 * resolveAgentAnswer() answers from site data with no model call. Measured on
 * the live site it served 96 of the first 103 answers -- for most visitors it
 * IS the agent. Anonymous visitors get one model answer a day, so anything the
 * data can answer must be answered here, and answered correctly.
 *
 * The rule that keeps it correct: a fast-path answer must answer the question
 * that was asked, or the question goes to the model. The first version matched
 * keywords and answered whatever the keyword was attached to, so "what runes
 * should I take on Jinx" returned an item list with no runes in it, and "is
 * Yasuo hard to play against" returned Yasuo's own difficulty.
 *
 * Everything that does go to the model gets buildAgentContext(), which now
 * carries the tier list by role, the latest patch, items and runes the question
 * names, every champion it names, and China's Legendary loadouts -- the model
 * used to say "the context does not contain that" to most real questions, and
 * named Rammus the best jungler from the beginner list because that was the
 * only champion list it had.
 */

const COMBOS = comboData as {
  champions?: Record<string, { combo?: string[]; why?: string; confidence?: string }>;
};

type ItemRecord = {
  name: string;
  slug: string;
  cost: number;
  category?: string;
  stats?: Record<string, { value: number; percent?: boolean }>;
  passives?: string[];
  tags?: string[];
};
type RuneRecord = { slug: string; tree?: string; type?: string; slot?: number; description?: string };

const ITEMS = itemsData as unknown as ItemRecord[];
const ITEM_BY_SLUG = new Map(ITEMS.map((item) => [item.slug, item]));
const RUNES = (engineData as unknown as { runes: Record<string, RuneRecord> }).runes;

const SLOT: Record<string, string> = { "1": "Q", "2": "W", "3": "E", "4": "R", auto: "Attack" };
const ROLES = ["Baron", "Jungle", "Mid", "Dragon", "Support"] as const;
type Role = (typeof ROLES)[number];
type Region = "EU" | "NA" | "CN";

const STAT_NAME: Record<string, string> = {
  hp: "Health", armor: "Armor", mr: "Magic Resist", ad: "Attack Damage", ap: "Ability Power",
  attackSpeed: "Attack Speed", abilityHaste: "Ability Haste", moveSpeed: "Move Speed",
  crit: "Crit Rate", lifesteal: "Lifesteal", physicalVamp: "Physical Vamp", omnivamp: "Omnivamp",
  mana: "Mana", hpRegen: "Health Regen", manaRegen: "Mana Regen", physicalPenFlat: "Armor Pen",
  physicalPenPct: "Armor Pen", magicPenFlat: "Magic Pen", magicPenPct: "Magic Pen", hsPower: "Heal and Shield Power",
};

/**
 * What the tiers mean, as the CODE assigns them -- not as the methodology page
 * words it. That page says the all-roles list uses fixed cutoffs of GOD 63%+
 * and so on, which is true only of each region's board, on a raw win rate the
 * site never shows: the board shows that rate shifted so the average champion
 * sits at 50% (EU by -9.4 points), so EU's GOD line is 53.6% on screen. The
 * Global list uses percentile bands instead. The agent quoted the page's
 * version for a day and would have told a reader Senna was GOD at 60.1% under
 * a 63% line.
 */
const TIER_MEANING = "Tiers run GOD, S, A, B, C and L, best to worst; L is the bottom tier. How a champion lands in "
  + "one depends on the view. The Global list ranks the blended win rate: GOD is the top 8%, S the next band to "
  + "25%, A to 50%, B to 75%, C to 92%, and L the bottom 8%. Each region's top 30 board uses fixed lines on its "
  + "top players' win rate (GOD 63%, S 61%, A 59%, B 57%, C 56%), but shows that rate shifted so the average "
  + "champion sits at 50%, so on screen the lines are about 9 to 10 points lower. Any role filter switches to "
  + "the same percentile bands within that role, so every role has a full spread. China's Tencent brackets use "
  + "their own lines on the whole-bracket win rate: GOD 53.5%, S 52%, A 50.8%, B 49.5%, C 48%.";

const TIER_KEYS: Record<string, string> = { god: "GOD", s: "S", a: "A", b: "B", c: "C", l: "Ass" };
const BAND_SHARE: Record<string, [number, number]> = {
  GOD: [0, 8], S: [8, 25], A: [25, 50], B: [50, 75], C: [75, 92], Ass: [92, 100],
};
/** Fixed lines on a region board's RAW win rate (web/data_loader.py). */
const RAW_LINE: Record<string, number> = { GOD: 63, S: 61, A: 59, B: 57, C: 56, Ass: 0 };
/** China's Tencent bracket lines, on the rate as shown (lib/cn.ts cnTier). */
const CN_LINE: Record<string, number> = { GOD: 53.5, S: 52, A: 50.8, B: 49.5, C: 48, Ass: 0 };
const TIER_UP: Record<string, string | null> = { GOD: null, S: "GOD", A: "S", B: "A", C: "B", Ass: "C" };
const REFRESH = "Ladder data is refreshed roughly twice a month: each refresh re-scrapes the top players of "
  + "every champion in each region. Tencent's China win rates behind patch winners and losers refresh daily.";

export interface AgentPageContext {
  pathname: string;
  page: string;
  site: ReturnType<typeof siteContext>;
  championSlug?: string;
  champion?: ReturnType<typeof championContext>;
  /** Other champions the question names, compact. "Ashe or Jinx" needs both. */
  alsoNamed?: ReturnType<typeof compactChampion>[];
  /** China Legendary win rate of each named champion against the other. */
  headToHead?: ReturnType<typeof headToHead>;
  items?: ReturnType<typeof itemCard>[];
  itemCatalogue?: { name: string; cost: number; category?: string; tags: string[] }[];
  runes?: { name: string; tree?: string; type?: string; text: string }[];
}

// ----------------------------------------------------------------- reading --
/** Possessives first, then the remaining apostrophes. Dropping apostrophes
 *  alone turns "Ornn's" into "ornns", which matches no champion, while
 *  Kai'Sa still has to come out as "kaisa". */
const unpossess = (value: string) => value.toLowerCase().replace(/’/g, "'").replace(/'s\b/g, "").replace(/'/g, "");

function normalizeQuestion(value: string): string {
  return unpossess(value).replace(/[^a-z0-9#%+]+/g, " ").trim();
}

const plain = (value: string) => unpossess(value).replace(/[^a-z0-9]+/g, " ").trim();

/**
 * Does answering need judgment rather than a lookup?
 *
 * These are the shapes that broke the old fast path: comparisons ("Ashe or
 * Jinx"), conditions ("against assassins"), advice ("how do I beat") and
 * hindsight ("still good after the nerf"). A keyword in one of those does not
 * make it a lookup; it makes it a question the data can inform but not settle.
 */
function needsReasoning(q: string): boolean {
  return /\b(why|still|worth|better|worse|vs|versus|against|or|instead|compare|pair|pairs|synergy|synergi[sz]e|beat|beating|deal with|into|tips?|explain|help me|improve|climb|climbing|how (do|to|can|should|would) i|how to|what if)\b/.test(q);
}

function roleFromQuestion(q: string): Role | null {
  if (/\b(jungle|jungler|junglers|jg)\b/.test(q)) return "Jungle";
  if (/\b(mid|midlane|middle|mid lane|midlaner)\b/.test(q)) return "Mid";
  // "top" is the Baron lane only when it is not "top 30", "top players" or
  // "top tier": the tier list asks about "China's top 30" and that is a
  // board, not a role filter.
  if (/\b(baron|toplane|top lane|toplaner|solo lane)\b|\btop\b(?!\s*(\d+|players?|tier|tiers|of|ranked|ranking))/.test(q)) return "Baron";
  if (/\b(dragon|adc|adcs|bot|botlane|bot lane|marksman|marksmen|carry)\b/.test(q)) return "Dragon";
  if (/\b(support|supports|supp|sup)\b/.test(q)) return "Support";
  return null;
}

function regionFromQuestion(q: string): Region | null {
  if (/\b(china|chinese|cn|tencent)\b/.test(q)) return "CN";
  if (/\b(eu|europe|european|euw|eune)\b/.test(q)) return "EU";
  if (/\b(na|north america|american|americas|us)\b/.test(q)) return "NA";
  return null;
}

/** Every champion the question names, longest name first so "Master Yi" is
 *  not also read as "Yi", in the order they appear in the question. */
function namedChampions(question: string): Champion[] {
  let haystack = ` ${plain(question)} `;
  const found: { champion: Champion; at: number }[] = [];
  const pool = [...getChampions(), ...pendingChampions()].sort((a, b) => b.name.length - a.name.length);
  for (const champion of pool) {
    for (const name of new Set([plain(champion.name), plain(champion.slug.replace(/-/g, " ")), champion.slug.replace(/-/g, "")])) {
      if (!name) continue;
      // "ornns tier" is a possessive typed without the apostrophe.
      let hit = name;
      let at = haystack.indexOf(` ${name} `);
      if (at < 0) {
        hit = `${name}s`;
        at = haystack.indexOf(` ${hit} `);
      }
      if (at < 0) continue;
      found.push({ champion, at });
      haystack = haystack.slice(0, at) + " " + "_".repeat(hit.length) + " " + haystack.slice(at + hit.length + 2);
      break;
    }
  }
  return found.sort((a, b) => a.at - b.at).map((entry) => entry.champion);
}

/** Resolve a champion named in a question so the assistant stays useful away
 * from champion pages. Longest name wins ("Master Yi" before "Yi"). */
export function championSlugFromQuestion(question: string): string {
  return namedChampions(question)[0]?.slug ?? "";
}

/**
 * Abbreviations the agent accepts inside a sentence. A subset of the item
 * pickers' list (lib/item-search.ts): in free text "cap", "sky" or "tf"
 * (Twisted Fate) would match by accident, so only acronyms and nicknames
 * that are not ordinary words count here.
 */
const AGENT_ITEM_ALIASES = new Set([
  "botrk", "bork", "brk", "ldr", "ie", "bt", "dd", "ga", "qss", "roa", "rfc", "dmp", "bc", "bms",
  "bft", "fon", "fh", "ibg", "kv", "pd", "sofw", "yg", "eon", "cpc", "dnd", "hs", "dcap",
  "zhonya", "zhonyas", "rabadon", "rabadons", "deathcap", "triforce", "shieldbow", "rageblade",
  "guinsoo", "guinsoos", "warmog", "warmogs", "morello", "liandry", "liandrys", "luden", "ludens",
  "nashor", "nashors", "rylai", "rylais", "sterak", "steraks", "youmuu", "youmuus", "ghostblade",
  "bloodmail", "twinguard", "hexplate", "duskblade", "kraken", "navori", "shojin", "serylda",
  "shurelya", "mikael", "mikaels", "randuin", "randuins", "dominik", "dominiks",
]);

function namedItems(question: string): ItemRecord[] {
  const haystack = ` ${plain(question)} `;
  return ITEMS
    .filter((item) => haystack.includes(` ${plain(item.name)} `)
      || (ITEM_ALIASES[item.slug] ?? []).some((alias) => AGENT_ITEM_ALIASES.has(alias) && haystack.includes(` ${alias} `)))
    .slice(0, 4);
}

/** What players actually type for runes with long names. Explicit rather
 *  than "any distinctive first word": "first" and "second" are first words
 *  too, and "which skill first" is not a question about First Strike. */
const RUNE_ALIASES: Record<string, string> = {
  grasp: "Grasp of the Undying", comet: "Arcane Comet", tempo: "Lethal Tempo",
  "lethal tempo": "Lethal Tempo", fleet: "Fleet Footwork", harvest: "Dark Harvest",
  overlord: "Ice Overlord", "phase rush": "Phase Rush", "first strike": "First Strike",
};

/** Runes by full name or a common short name. */
function namedRunes(question: string): string[] {
  const haystack = ` ${plain(question)} `;
  const names = new Set(Object.keys(RUNES).filter((name) => haystack.includes(` ${plain(name)} `)));
  for (const [alias, name] of Object.entries(RUNE_ALIASES)) {
    if (RUNES[name] && haystack.includes(` ${alias} `)) names.add(name);
  }
  return [...names].slice(0, 4);
}

function itemName(slug: string): string {
  return ITEM_BY_SLUG.get(slug)?.name ?? slug.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const pct = (value: number) => `${value.toFixed(1)}%`;

// ------------------------------------------------------------------ pieces --
function championFromPath(pathname: string, explicit?: string): Champion | undefined {
  const routeSlug = pathname.match(/^\/champions\/([^/?#]+)/)?.[1];
  return getChampion((explicit || routeSlug || "").toLowerCase());
}

function pageName(pathname: string): string {
  if (pathname.startsWith("/champions/")) return "champion profile";
  if (pathname.startsWith("/tier-list")) return "tier list";
  if (pathname.startsWith("/leaderboard")) return "leaderboard";
  if (pathname.startsWith("/build")) return "Build Studio";
  if (pathname.startsWith("/items")) return "item catalogue";
  if (pathname.startsWith("/runes")) return "runes and spells";
  if (pathname.startsWith("/regions")) return "regions and skill brackets";
  if (pathname.startsWith("/meta")) return "meta overview";
  if (pathname.startsWith("/methodology")) return "methodology";
  return "WRTrueMeta";
}

function regionRow(region: Region, slug: string) {
  const board = regionBoard(region);
  const champion = board.champions.find((entry) => entry.slug === slug);
  if (!champion || !Number.isFinite(champion.wr)) return null;
  return {
    region,
    tier: tierLabel(champion.tier),
    winRate: champion.wr,
    players: champion.nPlayers,
    collectedOn: board.collectedOn,
  };
}

function commonPlayerDepth(region: Region): number | null {
  const counts = new Map<number, number>();
  for (const champion of regionBoard(region).champions) {
    if (!champion.nPlayers || champion.nPlayers < 1) continue;
    counts.set(champion.nPlayers, (counts.get(champion.nPlayers) ?? 0) + 1);
  }
  let winner: number | null = null;
  let frequency = -1;
  for (const [depth, count] of counts) {
    if (count > frequency) { winner = depth; frequency = count; }
  }
  return winner;
}

function tierRank(tier: string): number {
  return ({ GOD: 0, S: 1, A: 2, B: 3, C: 4, Ass: 5 } as Record<string, number>)[tier] ?? 9;
}

function rolesOf(champion: Champion): string[] {
  return champion.roles?.length ? champion.roles : [champion.role];
}

/** The Global tier list, best first, optionally for one role. */
function globalRanking(role?: Role | null) {
  return getGlobalChampions()
    .filter((champion) => !champion.statsPending && Number.isFinite(champion.wr))
    .filter((champion) => !role || rolesOf(champion).includes(role))
    .sort((a, b) => tierRank(a.tier) - tierRank(b.tier) || b.wr - a.wr)
    .map((champion) => ({ name: champion.name, slug: champion.slug, role: champion.role, tier: tierLabel(champion.tier), winRate: champion.wr }));
}

function beginnerRecommendations(role?: Role | null) {
  // Difficulty first, but never into the bottom tiers: a low-complexity
  // champion who loses is a bad first champion. The old list offered Garen at
  // L tier and 45.5% to a new player because it sorted on difficulty alone.
  const candidates = getChampions()
    .filter((champion) => !champion.statsPending && Number.isFinite(champion.wr) && champion.difficulty <= 4)
    .filter((champion) => tierRank(champion.tier) <= 3)
    .filter((champion) => !role || rolesOf(champion).includes(role))
    .sort((left, right) => (
      left.difficulty - right.difficulty
      || tierRank(left.tier) - tierRank(right.tier)
      || right.wr - left.wr
    ));
  const usedRoles = new Set<string>();
  const picks: Array<{ name: string; slug: string; role: string; difficulty: number; difficultyLabel: string; tier: string; winRate: number }> = [];
  for (const champion of candidates) {
    const pickRole = role ?? rolesOf(champion).find((entry) => !usedRoles.has(entry)) ?? champion.role;
    if (!role && usedRoles.has(pickRole)) continue;
    usedRoles.add(pickRole);
    picks.push({
      name: champion.name,
      slug: champion.slug,
      role: pickRole,
      difficulty: champion.difficulty,
      difficultyLabel: champion.difficultyLabel,
      tier: tierLabel(champion.tier),
      winRate: champion.wr,
    });
    if (picks.length >= (role ? 4 : 6)) break;
  }
  return picks;
}

function regionalContrasts() {
  return getChampions()
    .map((champion) => {
      const rows = (["EU", "NA", "CN"] as const).map((region) => regionRow(region, champion.slug)).filter(Boolean);
      if (rows.length < 3) return null;
      const good = rows.filter((row) => row!.winRate >= 50);
      const bad = rows.filter((row) => row!.winRate < 50);
      if (good.length !== 2 || bad.length !== 1) return null;
      return {
        name: champion.name,
        slug: champion.slug,
        results: rows.map((row) => ({ region: row!.region, tier: row!.tier, winRate: row!.winRate })),
        spread: Math.max(...rows.map((row) => row!.winRate)) - Math.min(...rows.map((row) => row!.winRate)),
      };
    })
    .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry))
    .sort((left, right) => right.spread - left.spread)
    .slice(0, 8);
}

/** The latest patch: Riot's one-line reason per changed champion, plus the
 *  site's own write-up, which also covers items and runes. */
function latestPatch() {
  const champions = getChampions().flatMap((champion) => {
    const change = getChampionHistory(champion.name).changes
      .find((entry) => entry.patch === CURRENT_PATCH && entry.kind === "balance" && !entry.modeOnly);
    return change ? [{
      name: champion.name,
      slug: champion.slug,
      summary: change.summary,
      changes: change.changes.slice(0, 4).map((line) => `${line.ability}: ${line.text}`.replace(/\s+/g, " ").slice(0, 200)),
    }] : [];
  });
  const writeUp = CHANGELOG.find((entry) => entry.title.includes(`Patch ${CURRENT_PATCH}`));
  return {
    patch: CURRENT_PATCH,
    winRatesCollectedOn: WINRATE_PATCH,
    writeUp: writeUp?.body ?? null,
    champions,
  };
}

function siteContext() {
  const regions = (["EU", "NA", "CN"] as const).map((region) => {
    const board = regionBoard(region);
    return {
      region,
      playerPoolPerChampion: commonPlayerDepth(region),
      champions: board.nChampions,
      collectedOn: board.collectedOn,
    };
  });
  const depths = regions.map((region) => region.playerPoolPerChampion).filter((depth): depth is number => depth != null);
  return {
    trackedRegions: regions.map((region) => region.region),
    regions,
    currentPatch: CURRENT_PATCH,
    winRatePatch: WINRATE_PATCH,
    dataVsWinRates: `Ability, item and rune numbers are on patch ${CURRENT_PATCH}. The win rates and tiers were collected on ${WINRATE_PATCH}, so a champion changed since then shows its results from before the change until the next collection.`,
    tierMeaning: TIER_MEANING,
    refreshCadence: REFRESH,
    playerPoolMeaning: "The displayed player pool is per champion, per regional leaderboard, not split across regions.",
    globalMaximumPlayersPerChampion: depths.length === regions.length
      ? depths.reduce((total, depth) => total + depth, 0)
      : null,
    globalCalculation: "The Global win rate is the arithmetic mean of every available comparable regional board, with at least two regions required.",
    top30Methodology: "Top 30 is the current balance between high-skill signal, regional comparability, collection time and noise. Top 50 would add more coverage but materially increase scrape time and include a broader, less concentrated player sample.",
    chinaLoadouts: "Champion pages also carry China's Legendary-rank Classic Ranked loadout panel: the item cores, rune pages, boots, spells and matchups the whole Legendary population plays, each with its win rate and pick rate. That is a different population from the Top 30 boards.",
    tierListByRole: Object.fromEntries(ROLES.map((role) => [role, globalRanking(role).slice(0, 6)])),
    latestPatch: latestPatch(),
    beginnerRecommendations: beginnerRecommendations(),
    regionalContrasts: regionalContrasts(),
    tierListData: [
      "overall and role tier",
      "win rate",
      "player-pool depth (Top 30, Top 25, Top 10 or Top 5 where available)",
      "ceiling win rate",
      "median games",
      "movement since the previous collection",
      "role and class filters",
    ],
  };
}

/** China's Legendary loadout panel, compact: the top rows of each tab with
 *  their win and pick rates. Rows played under 1% of the time are dropped from
 *  the matchup extremes, where a 100% over three games would otherwise lead. */
function chinaLoadouts(slug: string) {
  const top = (tab: LoadoutTab | undefined, n: number) => (tab?.rows ?? []).slice(0, n).map((row) => ({
    picks: row.entities.map((entity) => entity.name).join(" + "),
    winRate: row.winRate,
    pickRate: row.pickRate,
  }));
  const popular = (tab: LoadoutTab | undefined, n: number) => [...(tab?.rows ?? [])]
    .sort((a, b) => (b.pickRate ?? 0) - (a.pickRate ?? 0)).slice(0, n)
    .map((row) => ({ picks: row.entities.map((entity) => entity.name).join(" + "), winRate: row.winRate, pickRate: row.pickRate }));
  return getChampionLoadouts(slug).map((lane) => {
    const versus = (lane.tabs.versus?.rows ?? []).filter((row) => (row.pickRate ?? 0) >= 1);
    const byWin = [...versus].sort((a, b) => (b.winRate ?? 0) - (a.winRate ?? 0));
    const name = (row: (typeof versus)[number]) => row.entities.map((entity) => entity.name).join(" + ");
    return {
      lane: lane.lane,
      capturedAt: lane.capturedAt.slice(0, 10),
      versusKind: lane.versusKind,
      mostPlayedItemCores: popular(lane.tabs.items, 3),
      highestWinItemCores: top(lane.tabs.items, 3),
      mostPlayedRunePages: popular(lane.tabs.runes, 3),
      boots: popular(lane.tabs.boots, 2),
      spells: popular(lane.tabs.spells, 2),
      bestMatchups: byWin.slice(0, 4).map((row) => ({ opponent: name(row), winRate: row.winRate, pickRate: row.pickRate })),
      worstMatchups: byWin.slice(-4).reverse().map((row) => ({ opponent: name(row), winRate: row.winRate, pickRate: row.pickRate })),
    };
  });
}

/** Each side's China Legendary win rate against the other, where recorded. */
function headToHead(a: Champion, b: Champion) {
  const versus = (self: Champion, other: Champion) => {
    for (const lane of getChampionLoadouts(self.slug)) {
      if (lane.versusKind !== "matchup") continue;
      const row = (lane.tabs.versus?.rows ?? []).find((entry) => entry.entities.some((entity) => entity.name === other.name));
      if (row) return { champion: self.name, lane: lane.lane, against: other.name, winRate: row.winRate, pickRate: row.pickRate };
    }
    return null;
  };
  return [versus(a, b), versus(b, a)].filter(Boolean);
}

function championContext(champion: Champion) {
  const details = getChampionDetails(champion.slug);
  const matchups = getMatchups(champion.slug);
  const history = getChampionHistory(champion.name);
  const combo = COMBOS.champions?.[champion.name] ?? null;
  const builds = buildsByServer(champion.name);
  const global = getGlobalBySlug(champion.slug);
  const podium = champion.globalBestPlayerPodium ?? champion.bestPlayerPodium;
  return {
    name: champion.name,
    slug: champion.slug,
    role: champion.role,
    roles: rolesOf(champion),
    class: champion.class,
    difficulty: champion.difficulty,
    difficultyLabel: champion.difficultyLabel,
    statsPending: Boolean(champion.statsPending),
    global: global && Number.isFinite(global.wr)
      ? { tier: tierLabel(global.tier), winRate: global.wr, movement: global.wrDelta ?? null }
      : null,
    regions: (["EU", "NA", "CN"] as const).map((region) => regionRow(region, champion.slug)).filter(Boolean),
    skillPriority: details?.skillPriority ?? [],
    abilities: (details?.abilities ?? []).map((ability) => ({
      key: ability.key,
      name: ability.name,
      text: ability.text.slice(0, 420),
    })),
    combo,
    matchups: {
      // Measured in China Legendary ranked (lib/counters.ts), not opinion.
      strong: matchups.strong.slice(0, 5).map((entry) => ({ name: entry.champion.name, winRate: entry.winRate, reason: entry.reason })),
      weak: matchups.weak.slice(0, 5).map((entry) => ({ name: entry.champion.name, winRate: entry.winRate, reason: entry.reason })),
    },
    recentChanges: history.changes.slice(0, 3).map((change) => ({
      patch: change.patch,
      kind: change.kind,
      summary: change.summary,
      changes: change.changes.slice(0, 5),
    })),
    bestPlayers: (podium?.players ?? []).slice(0, 3).map((player, index) => ({
      place: index + 1,
      name: player.player,
      server: player.server,
      winRate: player.winRate,
      games: player.games,
      championScore: player.championScore,
      score: player.score,
    })),
    // Names, not slugs: the first version printed "hexoptics-c44" to players.
    serverBuilds: Object.fromEntries(Object.entries(builds).map(([server, build]) => [server.toUpperCase(), build ? {
      items: build.items.map(itemName),
      boots: build.boots ? itemName(build.boots) : null,
      runes: [build.runes?.keystone, ...(build.runes?.minors ?? []), build.runes?.flex]
        .filter((rune): rune is string => Boolean(rune)),
      sampleOf: build.sampleOf,
      of: build.of,
    } : null])),
    chinaLegendaryLoadouts: chinaLoadouts(champion.slug),
  };
}

function compactChampion(champion: Champion) {
  const global = getGlobalBySlug(champion.slug);
  const matchups = getMatchups(champion.slug);
  const builds = buildsByServer(champion.name);
  const china = chinaLoadouts(champion.slug)[0];
  return {
    name: champion.name,
    slug: champion.slug,
    roles: rolesOf(champion),
    class: champion.class,
    difficulty: champion.difficulty,
    global: global && Number.isFinite(global.wr) ? { tier: tierLabel(global.tier), winRate: global.wr } : null,
    regions: (["EU", "NA", "CN"] as const).map((region) => regionRow(region, champion.slug)).filter(Boolean),
    strongInto: matchups.strong.slice(0, 4).map((entry) => entry.champion.name),
    weakInto: matchups.weak.slice(0, 4).map((entry) => entry.champion.name),
    mostBuiltEU: builds.eu ? builds.eu.items.map(itemName) : null,
    chinaMostPlayedCore: china?.mostPlayedItemCores[0] ?? null,
  };
}

function itemCard(item: ItemRecord) {
  const stats = Object.entries(item.stats ?? {}).map(([key, stat]) =>
    `${stat.value}${stat.percent ? "%" : ""} ${STAT_NAME[key] ?? key}`);
  return { name: item.name, cost: item.cost, category: item.category, stats, passives: item.passives ?? [] };
}

export function buildAgentContext(pathname: string, explicitChampionSlug?: string, question = ""): AgentPageContext {
  const safePath = pathname.startsWith("/") ? pathname.slice(0, 160) : "/";
  const champion = championFromPath(safePath, explicitChampionSlug);
  const q = normalizeQuestion(question);
  const others = namedChampions(question).filter((entry) => entry.slug !== champion?.slug).slice(0, 2);
  const items = namedItems(question);
  const runes = namedRunes(question);
  const wantsItems = /\bitems?\b/.test(q) || safePath.startsWith("/items");
  const wantsRunes = /\brunes?\b/.test(q) || safePath.startsWith("/runes");
  return {
    pathname: safePath,
    page: pageName(safePath),
    site: siteContext(),
    ...(champion ? { championSlug: champion.slug, champion: championContext(champion) } : {}),
    ...(others.length ? { alsoNamed: others.map(compactChampion) } : {}),
    ...(champion && others.length ? { headToHead: headToHead(champion, others[0]) } : {}),
    ...(items.length ? { items: items.map(itemCard) } : {}),
    // A general item question with no item named gets the whole catalogue in
    // short form, so "what items are good against tanks" has something to
    // reason over rather than nothing.
    ...(wantsItems && !items.length ? {
      itemCatalogue: ITEMS.map((item) => ({ name: item.name, cost: item.cost, category: item.category, tags: item.tags ?? [] })),
    } : {}),
    ...(runes.length || (wantsRunes && !champion) ? {
      runes: (runes.length ? runes : Object.keys(RUNES)).map((name) => ({
        name,
        tree: RUNES[name].tree,
        type: RUNES[name].type,
        text: (RUNES[name].description ?? "").slice(0, runes.length ? 600 : 160),
      })),
    } : {}),
  };
}

// ------------------------------------------------------------- fast answers --
function action(label: string, href: string) {
  return { label, href };
}

function latestChange(context: NonNullable<AgentPageContext["champion"]>, patch?: string | null) {
  // Riot leaves the summary blank on some entries; the change lines are the
  // substance. Printing summary alone produced "7.3:" with nothing after it.
  // A patch named in the question wins: "did 7.3a help Nocturne" is about
  // 7.3a even though his latest change is 7.3b.
  const change = context.recentChanges.find((entry) =>
    (entry.summary || entry.changes.length) && (!patch || entry.patch === patch));
  if (!change) return null;
  const lines = change.changes.map((line) => `${line.ability}: ${line.text}`.replace(/\s+/g, " "));
  return { change, lines };
}

function deterministicChampionAnswer(question: string, context: NonNullable<AgentPageContext["champion"]>): AgentAnswer | null {
  const q = normalizeQuestion(question);
  const reasoning = needsReasoning(q);
  const href = `/champions/${context.slug}`;
  const name = context.name;
  const region = regionFromQuestion(q);

  // Skill order is a lookup even when phrased as a choice ("max Q or E first").
  if (/\b(skill order|leveling order|level order|max order|what to max|which (skill|ability|spell) (first|to max)|max (q|w|e)|(q|w|e) first)\b/.test(q)) {
    const priority = context.skillPriority.join(" > ");
    if (!priority) return null;
    return {
      source: "data",
      answer: `Max ${name}'s abilities in this order: ${priority}. Put points in your ultimate whenever it is available.`,
      evidence: [`Skill priority: ${priority}`],
      actions: [action("See ability details", href)],
      followUps: [`What is ${name}'s combo?`, `What runes do top players use on ${name}?`],
    };
  }

  if (/\bcombos?\b/.test(q)) {
    const sequence = context.combo?.combo?.map((step) => SLOT[step] ?? step).join(" > ");
    if (!sequence) return null;
    return {
      source: "data",
      answer: [
        `${name}'s highest-damage sequence is ${sequence}.`,
        context.combo?.why ?? "",
        "Treat it as a damage reference: positioning, cooldowns and safety still decide the real sequence.",
      ].filter(Boolean).join("\n\n"),
      evidence: [`Combo: ${sequence}`],
      actions: [action("See ability details", href)],
      followUps: [`What is ${name}'s skill order?`, `Who counters ${name}?`],
    };
  }

  // China's own matchup numbers, when the question asks about China.
  if (region === "CN" && /\b(matchup|matchups|counter|counters|against|vs|lane against|best into|worst into)\b/.test(q)) {
    const lane = context.chinaLegendaryLoadouts.find((entry) => entry.versusKind === "matchup") ?? null;
    if (!lane || !lane.bestMatchups.length) return null;
    const row = (entry: { opponent: string; winRate: number; pickRate: number }) =>
      `${entry.opponent} (${pct(entry.winRate)} win, ${pct(entry.pickRate)} of games)`;
    return {
      source: "data",
      answer: `In China's Legendary ranked games, ${name} ${lane.lane} wins most against ${lane.bestMatchups.slice(0, 3).map(row).join(", ")}.\n\nThe hardest lanes are ${lane.worstMatchups.slice(0, 3).map(row).join(", ")}.\n\nMatchups played in under 1% of ${name}'s games are left out, because a handful of games can read 100%.`,
      evidence: [...lane.bestMatchups.slice(0, 2).map(row), ...lane.worstMatchups.slice(0, 2).map(row)],
      actions: [action("See all China matchups", href)],
      followUps: [`What do Chinese players build on ${name}?`, `What runes do top players use on ${name}?`],
    };
  }

  // "Did the patch help X?" -- answered with what the data can actually say.
  // The honest answer is often "nothing measures that yet", and it has to be
  // said that plainly: the boards and China's daily rates can both predate
  // the change, and quoting them as its effect would be inventing a result.
  if (/\b(help|helped|hurt|hurts|effect|impact|work|worked|stronger|weaker|better|worse|good now|bad now)\b/.test(q)
    && /\b(patch|buff|buffs|buffed|nerf|nerfs|nerfed|change|changes|changed|update|rework|\d+ \d+[a-z]?)\b/.test(q)) {
    const namedPatch = q.match(/\b(\d+ \d+[a-z]?)\b/)?.[1]?.replace(" ", ".") ?? null;
    const latest = latestChange(context, namedPatch);
    if (!latest) {
      // Asked about a patch that did not touch this champion: say so, and
      // name the change that did, rather than handing it to the model.
      const last = latestChange(context);
      if (!namedPatch || !last) return null;
      return {
        source: "data",
        answer: `${name} was not changed in patch ${namedPatch}. ${name}'s most recent change was in patch ${last.change.patch}${last.change.summary ? `: ${last.change.summary}` : "."}`,
        evidence: last.lines.slice(0, 3),
        actions: [action("Open patch history", href)],
        followUps: [`Did patch ${last.change.patch} help ${name}?`],
      };
    }
    const { change, lines } = latest;
    // Only a window that holds games on the patch measures it. A window that
    // names the patch but ends the day before it went live is drift.
    const mover = MOVERS_META.patch === change.patch && MOVERS_META.measuresPatch
      ? moverBySlug(context.slug) : null;
    const before = context.global
      ? `${name} is ${context.global.tier} tier at ${pct(context.global.winRate)} on the Global boards`
      : `${name} has no published Global result`;
    const measured = mover
      ? `In China (${MOVERS_META.scope}), ${name} went from ${pct(mover.oldWr)} before the patch to ${pct(mover.newWr)} after ${MOVERS_META.postPatchDays} ${MOVERS_META.postPatchDays === 1 ? "day" : "days"} of ${change.patch} games, a ${mover.delta >= 0 ? "gain" : "drop"} of ${Math.abs(mover.delta).toFixed(2)} points on a ${pct(mover.pickRate)} pick rate.${MOVERS_META.postPatchDays < 3 ? " That is very little data yet; small moves are noise." : ""}`
      : change.patch === CURRENT_PATCH && WINRATE_PATCH !== CURRENT_PATCH
        ? `Nothing on the site measures that yet. ${before}, but those boards were collected on ${WINRATE_PATCH}, before this change, and China's daily win rates do not include a day of ${change.patch} games yet. They will within a day or two, and this answer will use them.`
        : `${before}, collected on ${WINRATE_PATCH}, after this change. That shows where ${name} stands now, not a before and after.`;
    return {
      source: "data",
      answer: [
        `${name} was changed in patch ${change.patch}.`,
        change.summary,
        lines.length ? lines.slice(0, 4).join("\n") : "",
        measured,
      ].filter(Boolean).join("\n\n"),
      evidence: [...lines.slice(0, 2), mover ? `China: ${pct(mover.oldWr)} to ${pct(mover.newWr)}` : `Win rates collected on ${WINRATE_PATCH}`],
      actions: [action("Open patch history", href), action("Patch winners and losers", "/movers")],
      followUps: [`Where does ${name} rank now?`, `What runes do top players use on ${name}?`],
    };
  }

  if (reasoning) return null;

  if (/\b(difficult|difficulty|hard to (play|learn|master)|easy to (play|learn)|complex|complexity|mechanically)\b/.test(q)) {
    return {
      source: "data",
      answer: `${name} is rated ${context.difficulty}/10 for difficulty (${context.difficultyLabel}). That is WRTrueMeta's kit-complexity rating, not a claim that every matchup is equally easy.`,
      evidence: [`Difficulty: ${context.difficulty}/10`, `Label: ${context.difficultyLabel}`],
      actions: [action("Open champion profile", href)],
      followUps: [`What is ${name}'s skill order?`, `Who counters ${name}?`],
    };
  }

  if (/\b(counter|counters|countered|matchup|matchups|strong against|weak against|beats|good against|bad against)\b/.test(q)) {
    const show = (entry: { name: string; winRate: number }) => `${entry.name} (${entry.winRate.toFixed(1)}%)`;
    const weak = context.matchups.weak.map(show).join(", ");
    const strong = context.matchups.strong.map(show).join(", ");
    if (!weak && !strong) return null;
    return {
      source: "data",
      answer: `Measured in China Legendary ranked, ${name} struggles most into ${weak || "no matchup with enough games yet"}, and does best into ${strong || "no matchup with enough games yet"}. Each number is ${name}'s win rate in that matchup.`,
      evidence: [weak ? `Weak against: ${weak}` : "", strong ? `Strong against: ${strong}` : ""].filter(Boolean),
      actions: [action("Open champion profile", href), action("Create counter build", `/build?champion=${context.slug}&tab=generate`)],
      followUps: [`What are ${name}'s matchups in China?`, `What should I build against them?`],
    };
  }

  if (/\b(patch|patches|changed|change|changes|buff|buffed|buffs|nerf|nerfed|nerfs|update|updated|rework)\b/.test(q)) {
    const latest = latestChange(context);
    if (!latest) return null;
    const { change, lines } = latest;
    const live = change.patch === CURRENT_PATCH;
    return {
      source: "data",
      answer: [
        `${name} was last changed in patch ${change.patch}${live ? ", the current patch" : ""}.`,
        change.summary,
        lines.length ? lines.join("\n") : "",
        live && WINRATE_PATCH !== CURRENT_PATCH
          ? `${name}'s win rate on the site was collected on ${WINRATE_PATCH}, before this change, so it does not show the effect yet.`
          : "",
      ].filter(Boolean).join("\n\n"),
      evidence: lines.slice(0, 4),
      actions: [action("Open patch history", href)],
      followUps: [`Where does ${name} rank now?`, `What runes do top players use on ${name}?`],
    };
  }

  if (/\brunes?\b|\bkeystones?\b/.test(q)) {
    const servers = Object.entries(context.serverBuilds)
      .filter((entry): entry is [string, NonNullable<(typeof context.serverBuilds)[string]>] => Boolean(entry[1]?.runes?.length))
      .map(([server, build]) => `${server} top players: ${build.runes.join(", ")}`);
    const china = context.chinaLegendaryLoadouts[0];
    const chinaLines = (china?.mostPlayedRunePages ?? []).slice(0, 2)
      .map((page) => `China Legendary: ${page.picks} (${pct(page.winRate)} win, ${pct(page.pickRate)} of games)`);
    if (!servers.length && !chinaLines.length) return null;
    return {
      source: "data",
      answer: `Most-used ${name} rune pages:\n${[...servers, ...chinaLines].join("\n")}\n\nThe server lines are what each region's top 30 ${name} players run; the China lines are the whole Legendary-rank population, with how often each page wins.`,
      evidence: [...servers, ...chinaLines].slice(0, 4),
      actions: [action("Compare on the profile", href), action("Personalize in Build Studio", `/build?champion=${context.slug}&tab=generate`)],
      followUps: [`What items do top players build on ${name}?`, `What is ${name}'s skill order?`],
    };
  }

  if (/\bboots?\b|\bshoes\b/.test(q)) {
    const servers = Object.entries(context.serverBuilds)
      .filter((entry): entry is [string, NonNullable<(typeof context.serverBuilds)[string]>] => Boolean(entry[1]?.boots))
      .map(([server, build]) => `${server} top players: ${build.boots}`);
    const chinaLines = (context.chinaLegendaryLoadouts[0]?.boots ?? [])
      .map((boot) => `China Legendary: ${boot.picks} (${pct(boot.winRate)} win, ${pct(boot.pickRate)} of games)`);
    if (!servers.length && !chinaLines.length) return null;
    return {
      source: "data",
      answer: `Boots on ${name}:\n${[...servers, ...chinaLines].join("\n")}`,
      evidence: [...servers, ...chinaLines].slice(0, 4),
      actions: [action("Compare on the profile", href)],
      followUps: [`What items do top players build on ${name}?`, `What runes do top players use on ${name}?`],
    };
  }

  if (/\b(build|builds|items|item|core|most built|eu build|na build|cn build)\b/.test(q)) {
    const rows = Object.entries(context.serverBuilds)
      .filter((entry): entry is [string, NonNullable<(typeof context.serverBuilds)[string]>] => Boolean(entry[1]))
      .filter(([server]) => !region || server === region)
      .map(([server, build]) => `${server} top players: ${[...build.items, build.boots].filter(Boolean).join(", ")}`);
    const chinaLines = (!region || region === "CN" ? context.chinaLegendaryLoadouts[0]?.mostPlayedItemCores ?? [] : [])
      .slice(0, 2).map((core) => `China Legendary core: ${core.picks} (${pct(core.winRate)} win, ${pct(core.pickRate)} of games)`);
    if (!rows.length && !chinaLines.length) return null;
    return {
      source: "data",
      answer: `What ${name} players build:\n${[...rows, ...chinaLines].join("\n")}\n\nThese are what players actually built, not a recommendation for a particular enemy team. Build Studio does that.`,
      evidence: [...rows, ...chinaLines].slice(0, 4),
      actions: [action("Compare server builds", href), action("Personalize in Build Studio", `/build?champion=${context.slug}&tab=generate`)],
      followUps: [`What runes do top players use on ${name}?`, `What boots do players buy on ${name}?`],
    };
  }

  if (/\b(best|top|number 1|number one|#1)\b.*\bplayers?\b|\bwho plays\b|\bpodium\b/.test(q)) {
    if (!context.bestPlayers.length) return null;
    const lines = context.bestPlayers.map((player) =>
      `#${player.place} ${player.name}${player.server ? ` (${player.server})` : ""}${player.winRate != null ? `, ${pct(player.winRate)} win rate` : ""}${player.games != null ? ` over ${player.games} games` : ""}`,
    );
    return {
      source: "data",
      answer: `The current ${name} podium is:\n${lines.join("\n")}\n\nThe Best Player score weighs rank, champion-board position, Champion Score, win rate and games played.`,
      evidence: lines,
      actions: [action("Open leaderboard", "/leaderboard")],
      followUps: [`How is the Best Player score calculated?`, `What runes do top players use on ${name}?`],
    };
  }

  if (/\b(rank|ranking|ranked|tier|win rate|winrate|wr|performance|performing|strong|good|meta)\b/.test(q)) {
    if (context.statsPending) {
      return { source: "data", answer: `${name}'s leaderboard sample is still pending, so WRTrueMeta does not publish a tier or win rate for ${name} yet.`, actions: [action("Open profile", href)] };
    }
    const rows = context.regions.filter((row) => !region || row!.region === region);
    const regions = rows.map((row) => `${row!.region}: ${row!.tier} tier, ${pct(row!.winRate)} win rate`).join("\n");
    const global = context.global ? `${context.global.tier} tier at ${pct(context.global.winRate)} across the regional boards.` : "No blended global result is available yet.";
    return {
      source: "data",
      answer: region
        ? `${name} in ${region}: ${rows.length ? `${rows[0]!.tier} tier, ${pct(rows[0]!.winRate)} win rate` : "no published result"}.\n\nGlobally ${name} is ${global}`
        : `${name} is ${global}\n\nBy region:\n${regions}`,
      evidence: context.regions.map((row) => `${row!.region} sample: ${row!.players ?? "unknown"} players${row!.collectedOn ? `, collected ${row!.collectedOn}` : ""}`),
      actions: [action("Open champion profile", href), action("Compare tier lists", "/tier-list")],
      followUps: [`Why is ${name}'s win rate different by region?`, `Who is the best ${name} player?`],
    };
  }

  return null;
}

/** Which tier-list view a question is about. */
function tierView(q: string) {
  const region = regionFromQuestion(q);
  const bracket = /\b(diamond|master|challenger|legendary)\b/.exec(q)?.[1] ?? null;
  const tencent = region === "CN" && Boolean(bracket);
  // Tencent's brackets have no role tiers: tierRole equals tier there.
  const role = tencent ? null : roleFromQuestion(q);
  const scope = tencent
    ? `China's ${{ diamond: "Diamond+", master: "Master+", challenger: "Challenger", legendary: "Legendary" }[bracket!]} bracket`
    : region
      ? `${region === "CN" ? "China" : region}'s top 30 board`
      : "the Global list";
  return { region, role, tencent, scope: role ? `${scope}, among ${role} champions` : scope };
}

/** The champions a view ranks, best first, each with the tier it shows there. */
function tierPool(view: ReturnType<typeof tierView>) {
  const source = view.region && !view.tencent ? regionBoard(view.region).champions : getGlobalChampions();
  return source
    .filter((c) => !c.statsPending && Number.isFinite(c.wr))
    .filter((c) => !view.role || c.role === view.role)
    .map((c) => ({ name: c.name, slug: c.slug, wr: c.wr, tier: view.role ? c.tierRole : c.tier }))
    .sort((a, b) => b.wr - a.wr);
}

/** One tier's rule for a view, in the numbers that view shows. */
function bandRule(tier: string, view: ReturnType<typeof tierView>): string {
  const label = tierLabel(tier);
  if (view.tencent) {
    const up = TIER_UP[tier];
    return tier === "Ass"
      ? `${label} is everything under ${CN_LINE.C}% in this bracket's whole-ladder win rate.`
      : `${label} starts at ${CN_LINE[tier]}%${up ? ` and runs to just under ${CN_LINE[up]}%` : ""}, on the whole bracket's win rate.`;
  }
  if (view.region && !view.role) {
    const offset = regionBoard(view.region).wrOffset;
    const shown = (raw: number) => (raw + offset).toFixed(1);
    const up = TIER_UP[tier];
    const line = tier === "Ass"
      ? `${label} is everything under ${shown(RAW_LINE.C)}%`
      : `${label} starts at ${shown(RAW_LINE[tier])}%${up ? ` and runs to just under ${shown(RAW_LINE[up])}%` : ""}`;
    return `${line} on this board. The tiers are fixed lines on the top players' raw win rate (${label === "L" ? "under 56%" : `${RAW_LINE[tier]}%`}), and the board shows every rate shifted by ${offset} points so the average champion sits at 50%, which is why the line on screen is lower.`;
  }
  const [from, to] = BAND_SHARE[tier];
  return from === 0
    ? `${label} is the top ${to}% of the list, ranked by win rate.`
    : to === 100
      ? `${label} is the bottom ${100 - from}% of the list, ranked by win rate.`
      : `${label} is the band from the top ${from}% to the top ${to}% of the list, ranked by win rate.`;
}

/** "What puts a champion in S tier in EU?" */
function tierBandAnswer(q: string, tier: string): AgentAnswer {
  const view = tierView(q);
  const rule = bandRule(tier, view);
  if (view.tencent) {
    return {
      source: "data",
      answer: `In ${view.scope}, ${rule} Those are every player's games at that rank, not the top 30, which is why they sit close to 50%.`,
      evidence: [rule],
      actions: [action("Open tier list", "/tier-list"), action("Read methodology", "/methodology")],
    };
  }
  const pool = tierPool(view);
  const members = pool.filter((c) => c.tier === tier);
  const label = tierLabel(tier);
  const range = members.length
    ? `Right now that is ${members.length} champion${members.length === 1 ? "" : "s"}, from ${pct(members[0].wr)} down to ${pct(members[members.length - 1].wr)}: ${members.slice(0, 4).map((c) => c.name).join(", ")}${members.length > 4 ? " and others" : ""}.`
    : `No champion is in ${label} in this view right now.`;
  return {
    source: "data",
    answer: `On ${view.scope}: ${rule}\n\n${range}`,
    evidence: [rule, ...members.slice(0, 3).map((c) => `${c.name}: ${pct(c.wr)}`)],
    actions: [action("Open tier list", "/tier-list"), action("Read methodology", "/methodology")],
    followUps: members.slice(0, 2).map((c) => `Why is ${c.name} ${label} tier${view.region ? ` in ${view.region}` : ""}?`),
  };
}

/** "Why is Hwei GOD tier?" -- where the champion sits against its view's lines. */
function championTierAnswer(q: string, champion: Champion): AgentAnswer | null {
  const view = tierView(q);
  if (view.tencent) return null;
  const pool = tierPool(view);
  const index = pool.findIndex((c) => c.slug === champion.slug);
  if (index < 0) return null;
  const entry = pool[index];
  const label = tierLabel(entry.tier);
  const rule = bandRule(entry.tier, view);
  const above = index === 0 ? "the top of the list" : `with ${Math.round((index / pool.length) * 100)}% of the list above`;
  const up = TIER_UP[entry.tier];
  let gap = "";
  if (up && view.region && !view.role) {
    const nextLine = RAW_LINE[up] + regionBoard(view.region).wrOffset;
    gap = ` ${tierLabel(up)} starts at ${nextLine.toFixed(1)}%, ${(nextLine - entry.wr).toFixed(1)} points higher.`;
  } else if (up) {
    const needRank = Math.max(1, Math.floor((BAND_SHARE[up][1] / 100) * pool.length));
    gap = index + 1 > needRank ? ` ${tierLabel(up)} would need roughly rank ${needRank} or better.` : "";
  }
  return {
    source: "data",
    answer: `${champion.name} is ${label} tier on ${view.scope}: ${pct(entry.wr)}, ranked ${index + 1} of ${pool.length}, ${above}.\n\n${rule}${gap}`,
    evidence: [`${champion.name}: ${pct(entry.wr)}, rank ${index + 1} of ${pool.length}`, rule],
    actions: [action(`Open ${champion.name}`, `/champions/${champion.slug}`), action("Open tier list", "/tier-list")],
    followUps: [`Who counters ${champion.name}?`, `Did patch ${CURRENT_PATCH} help ${champion.name}?`],
  };
}

function rankingAnswer(champions: Champion[]): AgentAnswer {
  const rows = champions.map((champion) => {
    const global = getGlobalBySlug(champion.slug);
    return { name: champion.name, slug: champion.slug, tier: global ? tierLabel(global.tier) : null, wr: global?.wr ?? null, rank: global ? tierRank(global.tier) : 9 };
  }).sort((a, b) => a.rank - b.rank || (b.wr ?? 0) - (a.wr ?? 0));
  const lines = rows.map((row, index) => `${index + 1}. ${row.name}: ${row.tier ? `${row.tier} tier, ${pct(row.wr!)}` : "no published result"}`);
  return {
    source: "data",
    answer: `On the Global tier list, best first:\n${lines.join("\n")}\n\nThat is how their top players are doing. Which one suits you still depends on role and what you enjoy.`,
    evidence: lines,
    actions: rows.slice(0, 2).map((row) => action(`Open ${row.name}`, `/champions/${row.slug}`)),
    followUps: rows.slice(0, 2).map((row) => `Who counters ${row.name}?`),
  };
}

export function resolveAgentAnswer(question: string, context: AgentPageContext): AgentAnswer | null {
  const q = normalizeQuestion(question);
  const named = namedChampions(question);
  const reasoning = needsReasoning(q);
  const role = roleFromQuestion(q);

  if (/^(hi|hey|hello|yo|sup|hiya|good (morning|afternoon|evening)|thanks|thank you|thx|ty|ok|okay|cool|nice)( there| again| agent)?$/.test(q)) {
    const thanks = /thank|thx|ty/.test(q);
    return {
      source: "data",
      answer: thanks
        ? "Glad it helped. Ask about any champion, item, rune, matchup or the tier list."
        : "Hi. Ask about any champion, item, rune, matchup or the tier list: who is strongest in a role, what changed in the latest patch, what top players build, or who counters whom.",
      followUps: ["What changed in the latest patch?", "Who is the strongest ADC right now?"],
    };
  }
  if (/why.*top\s*30.*top\s*50|top\s*30.*instead.*top\s*50|top\s*30.*top\s*50/.test(q)) {
    return {
      source: "data",
      answer: "WRTrueMeta uses the top 30 players per champion and region as a deliberate trade between signal and coverage. It keeps the sample on the strongest ladder players while keeping EU, NA and CN collection fast enough to refresh consistently. Top 50 would add twenty more players per champion in each region, lengthen every collection and bring in a broader, noisier sample. Ranks 31 to 50 are not invalid; top 30 is simply the benchmark the tier list uses.",
      evidence: [context.site.top30Methodology, "EU, NA and CN are collected as separate regional samples"],
      actions: [action("Read methodology", "/methodology"), action("Compare tier list", "/tier-list")],
      followUps: ["How is the player pool counted?", "Why do regions have different results?"],
    };
  }
  if (/\b(player pool|pool size|sample size|top 30|30 per region|players per region)\b/.test(q)) {
    const rows = context.site.regions.map((region) =>
      `${region.region}: top ${region.playerPoolPerChampion ?? "unknown"} players per champion`,
    );
    return {
      source: "data",
      answer: `It is 30 players per champion, per region, not 30 shared across all three regions.\n\n${rows.join("\n")}\n\nSo a champion on the EU, NA and CN boards can contribute up to ${context.site.globalMaximumPlayersPerChampion ?? 90} player records to the Global view. Global averages the regional win rates; it does not merge every record into one 90-player list.`,
      evidence: rows,
      actions: [action("Open tier list", "/tier-list"), action("Read methodology", "/methodology")],
      followUps: ["Why do regions have different results?", "What data is available in the tier list?"],
    };
  }
  if (/\b(what|which).*regions?.*(tracked|available|included)|regions?.*(tracked|available|included)\b/.test(q)) {
    const regions = context.site.trackedRegions.join(", ");
    return {
      source: "data",
      answer: `The tier list currently tracks ${regions}. The Global view averages the available regional win rates for each champion and needs at least two regions.`,
      evidence: context.site.regions.map((region) => `${region.region}: ${region.champions} champions${region.collectedOn ? `, collected ${region.collectedOn}` : ""}`),
      actions: [action("Compare regions", "/tier-list"), action("Open regional analysis", "/regions")],
      followUps: ["Is the player pool 30 per region?", "Why do regions have different results?"],
    };
  }
  if (/\b(what|which).*data.*tier list|tier list.*(contain|include|show|available)\b/.test(q)) {
    return {
      source: "data",
      answer: `The tier list includes ${context.site.tierListData.join(", ")}. You can switch between Global, EU, NA and CN, then filter by role and player depth.`,
      evidence: context.site.tierListData,
      actions: [action("Open tier list", "/tier-list"), action("Read methodology", "/methodology")],
      followUps: ["What does GOD tier mean?", "Is the player pool 30 per region?"],
    };
  }
  if (/why.*regions?.*(different|differ)|regions?.*(different|differ).*why|regional.*difference/.test(q)) {
    return {
      source: "data",
      answer: "Each region is measured from its own top 30 champion-leaderboard players, so EU, NA and CN are three independent samples. Their results can differ because the player populations, builds, matchups and regional metas differ, plus ordinary sample variance.\n\nThe data shows the size of a gap, but on its own it cannot prove which of those causes produced a particular champion's gap. The Global view reduces reliance on one server by averaging the regional win rates.",
      evidence: [
        "EU, NA and CN use separate top 30 samples per champion",
        context.site.globalCalculation,
      ],
      actions: [action("Compare region results", "/tier-list"), action("Read methodology", "/methodology")],
      followUps: ["Is the player pool 30 per region?", "Which regions are tracked?"],
    };
  }
  if (/which champions?.*(good|strong).*2 regions?.*(bad|weak).*one|good in 2 regions?.*(bad|weak)|strong in two regions?.*(weak|bad)/.test(q)) {
    const examples = context.site.regionalContrasts;
    if (!examples.length) return {
      source: "data",
      answer: "No champion currently fits that split across all three regions. Try the regional tier-list comparison after the next collection.",
      actions: [action("Compare regions", "/tier-list")],
    };
    const lines = examples.slice(0, 5).map((entry) => `${entry.name}: ${entry.results.map((row) => `${row.region} ${pct(row.winRate)}`).join(", ")}`);
    return {
      source: "data",
      answer: `Using a 50% win rate as the line, these champions are above it in two regions and below it in one:\n${lines.join("\n")}\n\nThat describes the split; it does not prove a region caused it. Sample size, matchups and regional meta can all contribute.`,
      evidence: lines,
      actions: [action("Compare region results", "/regions"), action("Open tier list", "/tier-list")],
      followUps: ["Why do regions have different results?", "How is Global calculated?"],
    };
  }

  // A tier in a particular view: "what puts a champion in S tier in EU",
  // "why is Hwei GOD tier". Answered from the bands the code really uses.
  const namedTier = /\b(god|s|a|b|c|l) tier\b/.exec(q)?.[1] ?? null;
  // "why is ornn's tier so low" names no tier but asks the same thing.
  if (named.length === 1 && (namedTier ? /\bwhy\b|\bhow (is|come)\b|\bwhat (puts|makes|gets)\b/ : /\bwhy\b.*\btier(ed)?\b/).test(q)) {
    const answer = championTierAnswer(q, named[0]);
    if (answer) return answer;
  }
  if (namedTier && !named.length && /\bwhat (puts|makes|gets)\b|\b(mean|means|meaning|cutoff|cutoffs|threshold|line)\b|\bhow (do|does|is|are)\b/.test(q)) {
    return tierBandAnswer(q, TIER_KEYS[namedTier]);
  }

  // What the tiers mean, in general.
  if (/\b(god|s|a|b|c|l) tier\b.*\b(mean|means|meaning)\b|\btiers?\b.*\b(mean|means|meaning|work|cutoff|cutoffs|calculated|decided)\b|\bwhat is (god|l) tier\b/.test(q)) {
    return {
      source: "data",
      answer: context.site.tierMeaning,
      evidence: ["Global: percentile bands, GOD the top 8%", "Region boards: fixed lines on the raw top-player win rate", "Role filters: percentile bands within the role"],
      actions: [action("Read methodology", "/methodology"), action("Open tier list", "/tier-list")],
      followUps: ["Why are all the win rates above 50%?", "Is the player pool 30 per region?"],
    };
  }

  // How fresh the data is. Not when a champion is named: "what updated in
  // Nocturne" is about Nocturne's patch, not the collection schedule.
  if (!named.length && /\b(how often|how old|how fresh|up to date|last updated|last update|last collected|when (was|is|were|are|did|does|do).*\b(updated|update|refreshed|refresh|collected|collection))\b/.test(q)) {
    const rows = context.site.regions.map((region) => `${region.region}: collected ${region.collectedOn ?? "unknown"}`);
    return {
      source: "data",
      answer: `${context.site.refreshCadence}\n\nThe current boards:\n${rows.join("\n")}\n\n${context.site.dataVsWinRates}`,
      evidence: rows,
      actions: [action("Site updates", "/updates"), action("Read methodology", "/methodology")],
      followUps: ["What changed in the latest patch?", "Is the player pool 30 per region?"],
    };
  }

  // The latest patch, site-wide.
  if (!named.length && !reasoning && /\b(patch|patch notes|new patch|latest patch|what changed|whats new|buffed|buffs|nerfed|nerfs|who got (buffed|nerfed))\b/.test(q)
    && !/\b(best|strongest|highest|op|broken|meta|tier list)\b/.test(q)) {
    const patch = context.site.latestPatch;
    if (!patch.writeUp && !patch.champions.length) return null;
    const names = patch.champions.map((entry) => entry.name).join(", ");
    return {
      source: "data",
      answer: [
        `Patch ${patch.patch} is live.`,
        patch.writeUp ?? (names ? `Champions changed: ${names}.` : ""),
        patch.winRatesCollectedOn !== patch.patch
          ? `The win rates on the site were collected on ${patch.winRatesCollectedOn}, so they do not show this patch's effect yet.`
          : "",
      ].filter(Boolean).join("\n\n"),
      evidence: patch.champions.slice(0, 4).map((entry) => `${entry.name}: ${entry.summary.slice(0, 160)}`),
      actions: [action("What changed", "/updates"), action("Balance report", "/changes-report")],
      followUps: patch.champions.slice(0, 2).map((entry) => `What changed for ${entry.name}?`),
    };
  }

  // Anti-heal is the item question people actually ask, and the catalogue
  // tags it, so it needs no model.
  if (/\b(anti ?heal|grievous|against (heal|healing|healers|sustain|lifesteal|regen)|stop (heal|healing)|reduce (heal|healing)|counter (heal|healing))\b/.test(q)) {
    const items = ITEMS.filter((item) => item.tags?.includes("antiHeal")).sort((a, b) => a.cost - b.cost);
    if (!items.length) return null;
    const lines = items.map((item) => `${item.name} (${item.cost} gold, ${item.category ?? "item"})`);
    return {
      source: "data",
      answer: `These items apply Grievous Wounds, which cuts healing:\n${lines.join("\n")}\n\nPick the one that matches your class: the tank, fighter, marksman and mage options carry different stats.`,
      evidence: lines,
      actions: [action("Open items", "/items")],
      followUps: items.slice(0, 2).map((item) => `What does ${item.name} do?`),
    };
  }

  // Items and runes by name.
  const items = context.items ?? [];
  if (items.length && !reasoning && !named.length) {
    const cards = items.map((item) => [
      `${item.name}: ${item.cost} gold${item.category ? `, ${item.category}` : ""}`,
      item.stats.length ? `Stats: ${item.stats.join(", ")}` : "",
      ...item.passives,
    ].filter(Boolean).join("\n"));
    return {
      source: "data",
      answer: cards.join("\n\n"),
      evidence: items.map((item) => `${item.name}: ${item.cost} gold`),
      actions: [action("Open items", "/items")],
      followUps: ["What items are good against healing?"],
    };
  }
  const runes = context.runes ?? [];
  if (runes.length && runes.length <= 4 && !reasoning && !named.length && namedRunes(question).length) {
    return {
      source: "data",
      answer: runes.map((rune) => `${rune.name}${rune.type ? ` (${rune.tree ? `${rune.tree} ` : ""}${rune.type})` : ""}: ${rune.text}`).join("\n\n"),
      evidence: runes.map((rune) => rune.name),
      actions: [action("Open runes and spells", "/runes-spells")],
    };
  }

  // Several champions: rank them, unless the question wants a judgment.
  if (named.length >= 2 && !reasoning && /\b(rank|ranking|tier|tiers|win rate|winrate|stronger|strongest|compare|best|which)\b/.test(q)) {
    return rankingAnswer(named);
  }

  if (/newbie|beginner|new player|just starting|easy champions?|who should i (play|learn|main)|easy .*(champion|champ|to learn)/.test(q)) {
    const picks = beginnerRecommendations(role);
    if (!picks.length) return null;
    const lines = picks.map((entry) => `${entry.name} (${entry.role}), difficulty ${entry.difficulty}/10, ${entry.tier} tier, ${pct(entry.winRate)}`);
    return {
      source: "data",
      answer: `${role ? `For a new ${role} player` : "For a new player"}, start with a low-complexity champion that is also doing well, and learn one role at a time:\n${lines.join("\n")}\n\nThese are good starting points, not a promise that every matchup will be easy. Pick the one whose kit you enjoy.`,
      evidence: ["Difficulty 4/10 or lower, tier B or better, then tier and win rate", ...lines.slice(0, 3)],
      actions: [action("Explore champions", "/champions"), action("Open tier list", "/tier-list")],
      followUps: picks.slice(0, 2).map((entry) => `What is ${entry.name}'s skill order?`),
    };
  }

  // The best champions, overall or in a role. A named champion makes it a
  // synergy question ("best support for Jinx"), which the model answers.
  if (!named.length && !reasoning && /\b(best|strongest|top|highest win ?rate|highest wr|op|broken|meta|god tier|tier 1|most overpowered)\b/.test(q)
    && !/\bplayers?\b/.test(q)) {
    const ranking = globalRanking(role).slice(0, 5);
    if (!ranking.length) return null;
    const lines = ranking.map((entry, index) => `${index + 1}. ${entry.name}${role ? "" : ` (${entry.role})`}: ${entry.tier} tier, ${pct(entry.winRate)}`);
    return {
      source: "data",
      answer: `${role ? `The strongest ${role === "Dragon" ? "Dragon lane (ADC)" : role} champions` : "The strongest champions"} on the Global tier list right now:\n${lines.join("\n")}\n\nRanked by tier, then by how their top players are winning across EU, NA and China. ${context.site.dataVsWinRates}`,
      evidence: lines,
      actions: [action("Open tier list", "/tier-list"), ...ranking.slice(0, 1).map((entry) => action(`Open ${entry.name}`, `/champions/${entry.slug}`))],
      followUps: ranking.slice(0, 2).map((entry) => `What runes do top players use on ${entry.name}?`),
    };
  }

  if (/best player.*(score|scored|calculated)|how.*best player/.test(q)) {
    return {
      source: "data",
      answer: "The Best Player score combines confidence-adjusted win rate, current rank, champion-leaderboard position, Champion Score and current-season games. That stops someone being named #1 from a tiny lucky sample or from rank alone.",
      evidence: ["Current-season data", "Rank, board position, Champion Score, win rate and games"],
      actions: [action("Open global leaderboard", "/leaderboard")],
    };
  }
  if (/how.*win rate|where.*win rate|win rate.*calculated/.test(q) && !named.length) {
    return {
      source: "data",
      answer: "WRTrueMeta collects current-season results from the top champion-leaderboard players in each region. Regional boards stay separate, and the Global view blends comparable regional samples rather than mixing in unrelated public bracket statistics.",
      actions: [action("Open tier list", "/tier-list"), action("Open meta overview", "/meta")],
    };
  }
  if (/what.*build studio|how.*build studio|what.*optimi[sz]/.test(q)) {
    return {
      source: "data",
      answer: "Build Studio combines the fight engine with model judgment. The engine compares measurable damage and durability across targets; the model handles practical effects, conditional passives and real-game tradeoffs. Full build generation has its own daily allowance, so the site agent sends you there rather than spending one quietly.",
      actions: [action("Open Build Studio", "/build")],
    };
  }

  // A champion question. Only when the question names at most one champion:
  // "how do I beat Darius as Garen" is about two, and answering from one
  // champion's data alone is how the old version answered a different question.
  if (context.champion && named.length <= 1) {
    const answer = deterministicChampionAnswer(question, context.champion);
    if (answer) return answer;
  }
  return null;
}
