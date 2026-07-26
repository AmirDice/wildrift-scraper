/** Scrape official China Wild Rift win/pick/ban rates from Tencent. */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const ROOT = process.cwd();
const SITE = path.join(ROOT, "web-next", "src", "data", "site.json");
const NEW_CHAMPIONS = path.join(ROOT, "web-next", "src", "data", "new_champions.json");
const NAME_MAP = path.join(ROOT, "data", "cn_hero_map.json");
const OUT = path.join(ROOT, "data", "cn_winrates.json");
const WEB_OUT = path.join(ROOT, "web-next", "src", "data", "cn.json");
const PREVIOUS_OUT = path.join(ROOT, "data", "cn_winrates_prev.json");
const MOVERS_OUT = path.join(ROOT, "web-next", "src", "data", "cn_movers.json");

const HERO_LIST_URL = "https://game.gtimg.cn/images/lgamem/act/lrlib/js/heroList/hero_list.js";
const RANK_URL = "https://mlol.qt.qq.com/go/lgame_battle_info/hero_rank_list_v2";
const HEADERS = { "User-Agent": "Mozilla/5.0", Referer: "https://lolm.qq.com/" };
const BRACKET_LABELS = {
  "1": "Diamond+",
  "2": "Master+",
  "3": "Challenger",
  "4": "Legendary",
};
const DEFAULT_BRACKET = "3";
const POSITION_LABELS = { "1": "Mid", "2": "Baron", "3": "Dragon", "4": "Support", "5": "Jungle" };

const jsonFile = async (file) => JSON.parse(await readFile(file, "utf8"));
const slug = (name) => name.toLowerCase().replaceAll("&", "and").replaceAll("'", "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

async function fetchJson(url) {
  const response = await fetch(url, { headers: HEADERS });
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

async function main() {
  const site = await jsonFile(SITE);
  const newChampions = await jsonFile(NEW_CHAMPIONS);
  const heroMap = await jsonFile(NAME_MAP);
  const checkedInPrevious = await jsonFile(OUT).catch(() => null);
  const euRole = new Map(
    [...site.champions, ...newChampions.champions].map((champion) => [champion.name, champion.role]),
  );
  const heroPayload = await fetchJson(HERO_LIST_URL);
  const cnNames = Object.fromEntries(Object.entries(heroPayload.heroList).map(([id, hero]) => [id, hero.name]));
  const rankPayload = await fetchJson(RANK_URL);
  const rank = rankPayload.data;
  if (!rank || typeof rank !== "object") throw new Error("Tencent rank response did not contain data");

  let date = null;
  const champions = new Map();
  const unmapped = new Set();

  for (const [bracket, positions] of Object.entries(rank)) {
    // Tencent's public page only exposes keys 1-4. Key 0 is legacy/internal
    // data and is explicitly discarded by the official frontend.
    if (!BRACKET_LABELS[bracket]) continue;
    for (const [position, entries] of Object.entries(positions)) {
      for (const entry of entries) {
        const heroId = String(entry.hero_id);
        const name = heroMap[heroId];
        if (!name) {
          unmapped.add(`${heroId}:${cnNames[heroId] ?? "unknown"}`);
          continue;
        }
        date ||= entry.dtstatdate || null;
        if (!champions.has(name)) {
          champions.set(name, {
            name,
            slug: slug(name),
            heroId,
            cnName: cnNames[heroId] ?? "",
            byBracket: {},
          });
        }

        const record = champions.get(name);
        const candidate = {
          winRate: Number(entry.win_rate_percent),
          pickRate: Number(entry.appear_rate_percent),
          banRate: Number(entry.forbid_rate_percent),
          strength: Number(entry.strength_level),
          position: POSITION_LABELS[position] ?? position,
        };
        const targetRole = euRole.get(name);
        const stored = record.byBracket[bracket];
        const candidateMatches = candidate.position === targetRole;
        const storedMatches = stored?.position === targetRole;
        const take = !stored
          ? true
          : candidateMatches !== storedMatches
            ? candidateMatches
            : candidate.pickRate > stored.pickRate;
        if (take) {
          record.byBracket[bracket] = candidate;
        }
      }
    }
  }

  if (unmapped.size) console.warn(`Skipped ${unmapped.size} unmapped heroes: ${[...unmapped].join(", ")}`);
  const sorted = [...champions.values()].sort((left, right) => left.name.localeCompare(right.name));
  const output = {
    source: "lolm.qq.com (official China server data)",
    date,
    bracketLabels: BRACKET_LABELS,
    defaultBracket: DEFAULT_BRACKET,
    nChampions: sorted.length,
    champions: sorted,
  };
  const payload = `${JSON.stringify(output, null, 2)}\n`;
  await Promise.all([writeFile(OUT, payload, "utf8"), writeFile(WEB_OUT, payload, "utf8")]);

  // Compare every published bracket with the last checked-in scrape. A
  // same-day rerun falls back to the preserved pre-refresh file so manually
  // rerunning the job does not erase every movement indicator.
  let previous = checkedInPrevious;
  if (!previous || previous.date === date) previous = await jsonFile(PREVIOUS_OUT).catch(() => null);
  const previousBySlug = new Map((previous?.champions ?? []).map((champion) => [champion.slug, champion]));
  const moversByBracket = {};
  for (const bracket of Object.keys(BRACKET_LABELS)) {
    moversByBracket[bracket] = sorted.flatMap((champion) => {
      const oldEntry = previousBySlug.get(champion.slug)?.byBracket?.[bracket];
      const newEntry = champion.byBracket[bracket];
      if (!oldEntry || !newEntry) return [];
      return [{
        slug: champion.slug,
        name: champion.name,
        oldWr: oldEntry.winRate,
        newWr: newEntry.winRate,
        delta: Math.round((newEntry.winRate - oldEntry.winRate) * 100) / 100,
        pickRate: newEntry.pickRate,
      }];
    }).sort((left, right) => right.delta - left.delta);
  }
  const movers = moversByBracket[DEFAULT_BRACKET];
  await writeFile(MOVERS_OUT, `${JSON.stringify({
    beforeDate: previous?.date ?? "",
    afterDate: date,
    patch: "",
    scope: "China · Challenger",
    defaultBracket: DEFAULT_BRACKET,
    bracketLabels: BRACKET_LABELS,
    champions: movers,
    byBracket: moversByBracket,
  }, null, 2)}\n`, "utf8");

  const snapshotDate = /^\d{8}$/.test(date ?? "")
    ? `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}`
    : date || "unknown";
  const historyDir = path.join(ROOT, "data", "history", "cn");
  await mkdir(historyDir, { recursive: true });
  const snapshotChampions = {};
  for (const champion of sorted) {
    const entry = champion.byBracket[DEFAULT_BRACKET];
    if (entry) snapshotChampions[champion.slug] = { wr: entry.winRate, pick: entry.pickRate, ban: entry.banRate };
  }
  await writeFile(
    path.join(historyDir, `${snapshotDate}.json`),
    `${JSON.stringify({ date: snapshotDate, region: "cn", champions: snapshotChampions }, null, 2)}\n`,
    "utf8",
  );
  console.log(`Wrote CN data for ${sorted.length} champions, source date ${date}, ${Object.keys(BRACKET_LABELS).length} published brackets, ${movers.length} Challenger movement rows.`);
}

await main();
