import comboData from "@/data/champion_combos.json";
import { getChampion, getChampions, pendingChampions, regionBoard, tierLabel, type Champion } from "@/lib/data";
import { getGlobalBySlug } from "@/lib/cn";
import { getChampionDetails } from "@/lib/champion-details";
import { getChampionHistory } from "@/lib/champion-history";
import { getMatchups } from "@/lib/counters";
import { buildsByServer } from "@/lib/ladder-build";
import type { AgentAnswer } from "@/lib/agent-types";

const COMBOS = comboData as {
  champions?: Record<string, { combo?: string[]; why?: string; confidence?: string }>;
};

const SLOT: Record<string, string> = { "1": "Q", "2": "W", "3": "E", "4": "R", auto: "Attack" };

export interface AgentPageContext {
  pathname: string;
  page: string;
  site: ReturnType<typeof siteContext>;
  championSlug?: string;
  champion?: ReturnType<typeof championContext>;
}

function normalizeQuestion(value: string): string {
  return value.toLowerCase().replace(/[’']/g, "").replace(/[^a-z0-9#%+]+/g, " ").trim();
}

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
  if (pathname.startsWith("/win-rates")) return "win rates";
  return "WRTrueMeta";
}

function regionRow(region: "EU" | "NA" | "CN", slug: string) {
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

function commonPlayerDepth(region: "EU" | "NA" | "CN"): number | null {
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

function beginnerRecommendations() {
  const candidates = getChampions()
    .filter((champion) => !champion.statsPending && Number.isFinite(champion.wr) && champion.difficulty <= 4)
    .sort((left, right) => (
      left.difficulty - right.difficulty
      || tierRank(left.tier) - tierRank(right.tier)
      || right.wr - left.wr
    ));
  const usedRoles = new Set<string>();
  const picks: Array<{ name: string; slug: string; role: string; difficulty: number; difficultyLabel: string; tier: string; winRate: number }> = [];
  for (const champion of candidates) {
    const role = (champion.roles ?? [champion.role]).find((entry) => !usedRoles.has(entry)) ?? champion.role;
    if (usedRoles.has(role)) continue;
    usedRoles.add(role);
    picks.push({
      name: champion.name,
      slug: champion.slug,
      role,
      difficulty: champion.difficulty,
      difficultyLabel: champion.difficultyLabel,
      tier: tierLabel(champion.tier),
      winRate: champion.wr,
    });
    if (picks.length >= 6) break;
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
    playerPoolMeaning: "The displayed player pool is per champion, per regional leaderboard—not split across regions.",
    globalMaximumPlayersPerChampion: depths.length === regions.length
      ? depths.reduce((total, depth) => total + depth, 0)
      : null,
    globalCalculation: "The Global win rate is the arithmetic mean of every available comparable regional board, with at least two regions required.",
    top30Methodology: "Top 30 is the current balance between high-skill signal, regional comparability, collection time and noise. Top 50 would add more coverage but materially increase scrape time and include a broader, less concentrated player sample.",
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
      strong: matchups.strong.slice(0, 5).map((entry) => ({ name: entry.champion.name, reason: entry.reason })),
      weak: matchups.weak.slice(0, 5).map((entry) => ({ name: entry.champion.name, reason: entry.reason })),
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
    serverBuilds: Object.fromEntries(Object.entries(builds).map(([server, build]) => [server.toUpperCase(), build ? {
      items: build.items,
      boots: build.boots,
      runes: build.runes,
      sampleOf: build.sampleOf,
      of: build.of,
    } : null])),
  };
}

export function buildAgentContext(pathname: string, explicitChampionSlug?: string): AgentPageContext {
  const safePath = pathname.startsWith("/") ? pathname.slice(0, 160) : "/";
  const champion = championFromPath(safePath, explicitChampionSlug);
  return {
    pathname: safePath,
    page: pageName(safePath),
    site: siteContext(),
    ...(champion ? { championSlug: champion.slug, champion: championContext(champion) } : {}),
  };
}

/** Resolve a champion named in a question so the assistant stays useful away
 * from champion pages. Longest name wins ("Master Yi" before "Yi"). */
export function championSlugFromQuestion(question: string): string {
  const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const haystack = ` ${normalize(question)} `;
  const champions = [...getChampions(), ...pendingChampions()]
    .sort((left, right) => right.name.length - left.name.length);
  return champions.find((champion) => {
    const names = [normalize(champion.name), normalize(champion.slug.replace(/-/g, " "))];
    return names.some((name) => name && haystack.includes(` ${name} `));
  })?.slug ?? "";
}

function action(label: string, href: string) {
  return { label, href };
}

function deterministicChampionAnswer(question: string, context: NonNullable<AgentPageContext["champion"]>): AgentAnswer | null {
  const q = normalizeQuestion(question);
  const analytical = q.startsWith("why ") || q.includes(" why ");
  const href = `/champions/${context.slug}`;
  const name = context.name;

  if (!analytical && /\b(difficult|difficulty|hard|easy)\b/.test(q)) {
    return {
      source: "data",
      answer: `${name} is rated ${context.difficulty}/10 for difficulty (${context.difficultyLabel}). That is WRTrueMeta's kit-complexity rating, not a claim that every matchup is equally easy.`,
      evidence: [`Difficulty: ${context.difficulty}/10`, `Label: ${context.difficultyLabel}`],
      actions: [action("Open champion profile", href)],
      followUps: [`What is ${name}'s skill combo?`, `Who counters ${name}?`],
    };
  }

  if (analytical && /\b(win rate|winrate|low|bad|weak)\b/.test(q) && context.global) {
    const regional = context.regions.map((row) => `${row!.region}: ${row!.winRate.toFixed(1)}%`).join(", ");
    return {
      source: "data",
      answer: `${name}'s current global result is ${context.global.winRate.toFixed(1)}% (${context.global.tier} tier)${regional ? `, with ${regional} region results` : ""}. The data shows the outcome, but it does not identify one proven cause for a low result. A reasonable inference is that matchup spread, regional meta, sample composition and player familiarity may all contribute; treat that as context, not a measured diagnosis.`,
      evidence: [
        `Global: ${context.global.winRate.toFixed(1)}% WR`,
        ...context.regions.map((row) => `${row!.region}: ${row!.winRate.toFixed(1)}% WR`),
      ],
      actions: [action("Open champion profile", href), action("Compare tier lists", "/tier-list")],
      followUps: [`What are ${name}'s hard matchups?`, `What changed for ${name} recently?`],
    };
  }

  if (/\b(combo|skill order|max order|ability order)\b/.test(q)) {
    const sequence = context.combo?.combo?.map((step) => SLOT[step] ?? step).join(" → ");
    const priority = context.skillPriority.join(" → ");
    if (!sequence && !priority) return null;
    return {
      source: "data",
      answer: [
        sequence ? `${name}'s suggested highest-damage sequence is ${sequence}.` : "",
        context.combo?.why ?? "",
        priority ? `Max skills in this order: ${priority}.` : "",
        "Treat the combo as a damage reference—positioning, cooldowns and safety still decide the real sequence.",
      ].filter(Boolean).join("\n\n"),
      evidence: [sequence ? `Combo: ${sequence}` : "", priority ? `Skill priority: ${priority}` : ""].filter(Boolean),
      actions: [action("See ability details", href)],
      followUps: [`How difficult is ${name}?`, `What changed for ${name} recently?`],
    };
  }

  if (!analytical && /\b(counter|counters|matchup|strong against|weak against|beats)\b/.test(q)) {
    const weak = context.matchups.weak.map((entry) => entry.name).join(", ");
    const strong = context.matchups.strong.map((entry) => entry.name).join(", ");
    if (!weak && !strong) return null;
    return {
      source: "data",
      answer: `${name} is currently listed as weak into ${weak || "no confirmed matchups yet"}. ${name} is listed as strong into ${strong || "no confirmed matchups yet"}. Open the profile for the matchup-specific reasons.`,
      evidence: [weak ? `Weak against: ${weak}` : "", strong ? `Strong against: ${strong}` : ""].filter(Boolean),
      actions: [action("Open champion profile", href), action("Create counter build", `/build?champion=${context.slug}&tab=generate`)],
      followUps: [`Why is ${name} weak into those champions?`, `What build should I use against them?`],
    };
  }

  if (/\b(best.*player|top.*player|number 1|number one|#1)\b/.test(q)) {
    if (!context.bestPlayers.length) return null;
    const lines = context.bestPlayers.map((player) =>
      `#${player.place} ${player.name}${player.server ? ` (${player.server})` : ""}${player.winRate != null ? ` — ${player.winRate.toFixed(1)}% WR` : ""}${player.games != null ? ` over ${player.games} games` : ""}`,
    );
    return {
      source: "data",
      answer: `The current ${name} podium is:\n${lines.join("\n")}\n\nThe Best Player score weighs rank, champion-board position, Champion Score, win rate and games played.`,
      evidence: lines,
      actions: [action("Open leaderboard", "/leaderboard")],
      followUps: [`How is the Best Player score calculated?`, `What is ${name}'s win rate?`],
    };
  }

  if (/\b(patch|recent change|changed|buff|nerf|update)\b/.test(q)) {
    if (!context.recentChanges.length) return null;
    const lines = context.recentChanges.map((change) => `${change.patch}: ${change.summary}`);
    return {
      source: "data",
      answer: `${name}'s latest recorded changes are:\n${lines.join("\n")}`,
      evidence: lines,
      actions: [action("Open patch history", href)],
      followUps: [`Did those changes help ${name}?`, `Where does ${name} rank now?`],
    };
  }

  if (!analytical && /\b(build|items|runes|server build|most built|eu build|na build|cn build)\b/.test(q)) {
    const rows = Object.entries(context.serverBuilds)
      .filter((entry): entry is [string, NonNullable<(typeof context.serverBuilds)[string]>] => Boolean(entry[1]))
      .map(([server, build]) => `${server}: ${[...build.items, build.boots].filter(Boolean).join(" → ")}`);
    if (!rows.length) return null;
    return {
      source: "data",
      answer: `Most-built ${name} paths by server:\n${rows.join("\n")}\n\nThese copy what top ladder players built; they are not a personalized recommendation for a specific enemy team.`,
      evidence: rows,
      actions: [action("Compare server builds", href), action("Personalize in Build Studio", `/build?champion=${context.slug}&tab=generate`)],
      followUps: [`Why do the ${name} builds differ by server?`, `Which ${name} build fits my matchup?`],
    };
  }

  if (!analytical && /\b(rank|ranking|tier|win rate|winrate|performance)\b/.test(q)) {
    if (context.statsPending) {
      return { source: "data", answer: `${name}'s leaderboard sample is still pending, so WRTrueMeta does not publish a tier or win rate for ${name} yet.`, actions: [action("Open profile", href)] };
    }
    const regions = context.regions.map((row) => `${row!.region}: ${row!.tier} tier, ${row!.winRate.toFixed(1)}% WR`).join("\n");
    const global = context.global ? `${context.global.tier} tier at ${context.global.winRate.toFixed(1)}% WR across the available regional boards.` : "No blended global result is available yet.";
    return {
      source: "data",
      answer: `${name} is ${global}\n\nBy region:\n${regions}`,
      evidence: context.regions.map((row) => `${row!.region} sample: ${row!.players ?? "—"} players${row!.collectedOn ? `, collected ${row!.collectedOn}` : ""}`),
      actions: [action("Open champion profile", href), action("Compare tier lists", "/tier-list")],
      followUps: [`Why is ${name}'s win rate different by region?`, `Who is the best ${name} player?`],
    };
  }

  return null;
}

export function resolveAgentAnswer(question: string, context: AgentPageContext): AgentAnswer | null {
  const q = normalizeQuestion(question);
  if (/why.*top\s*30.*top\s*50|top\s*30.*instead.*top\s*50|top\s*30.*top\s*50/.test(q)) {
    return {
      source: "data",
      answer: `WRTrueMeta uses Top 30 players per champion and region as a deliberate signal-versus-coverage tradeoff. It keeps the sample concentrated on the strongest ladder players while keeping EU, NA and CN collection fast enough to refresh consistently. Top 50 would add ten more players per champion in each region, increasing scrape time and introducing a broader, noisier sample. That does not mean ranks 31–50 are invalid—it means Top 30 is the current benchmark used for comparable tier-list results.`,
      evidence: [context.site.top30Methodology, "EU, NA and CN are collected as separate regional samples"],
      actions: [action("Read methodology", "/methodology"), action("Compare tier list", "/tier-list")],
      followUps: ["How is the player pool counted?", "Why do regions have different results?"],
    };
  }
  if (/\b(player pool|pool size|sample size|top 30|30 per region|players per region)\b/.test(q)) {
    const rows = context.site.regions.map((region) =>
      `${region.region}: Top ${region.playerPoolPerChampion ?? "—"} players per champion`,
    );
    return {
      source: "data",
      answer: `It is 30 players per champion, per region—not 30 shared across all three regions.\n\n${rows.join("\n")}\n\nSo a champion represented on EU, NA and CN can contribute up to ${context.site.globalMaximumPlayersPerChampion ?? 90} player records to the Global view. Global averages the regional win rates; it does not merge all records into one unweighted 90-player list.`,
      evidence: rows,
      actions: [action("Open tier list", "/tier-list"), action("Read methodology", "/methodology")],
      followUps: ["Why do regions have different results?", "What data is available in the tier list?"],
    };
  }
  if (/\b(what|which).*regions?.*(tracked|available|included)|regions?.*(tracked|available|included)\b/.test(q)) {
    const regions = context.site.trackedRegions.join(", ");
    return {
      source: "data",
      answer: `The comparable top-player tier-list boards currently tracked are ${regions}. The Global view averages the available regional win rates for each champion and requires at least two regions.`,
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
      followUps: ["How are win rates calculated?", "Is the player pool 30 per region?"],
    };
  }
  if (/why.*regions?.*(different|differ)|regions?.*(different|differ).*why|regional.*difference/.test(q)) {
    return {
      source: "data",
      answer: "Each region is measured from its own Top 30 champion-leaderboard players, so EU, NA and CN are three independent samples. Their results can differ because the player populations, builds, matchups and regional metas differ, plus ordinary sample variance.\n\nWRTrueMeta can measure the gap, but the aggregate win-rate data alone cannot prove which one of those factors caused a specific champion's gap. The Global view reduces reliance on one server by averaging the available regional win rates.",
      evidence: [
        "EU, NA and CN use separate Top 30 samples per champion",
        context.site.globalCalculation,
      ],
      actions: [action("Compare region results", "/tier-list"), action("Read methodology", "/methodology")],
      followUps: ["Is the player pool 30 per region?", "What regions are currently tracked in the tier list?"],
    };
  }
  if (/which champions?.*(good|strong).*2 regions?.*(bad|weak).*one|good in 2 regions?.*(bad|weak)|strong in two regions?.*(weak|bad)/.test(q)) {
    const examples = context.site.regionalContrasts;
    if (!examples.length) return {
      source: "data",
      answer: "I do not have a three-region split that meets that definition in the current snapshot. Try the regional tier-list comparison after the next collection.",
      actions: [action("Compare regions", "/tier-list")],
    };
    const lines = examples.slice(0, 5).map((entry) => `${entry.name}: ${entry.results.map((row) => `${row.region} ${row.winRate.toFixed(1)}%`).join(" · ")}`);
    return {
      source: "data",
      answer: `Using 50% win rate as the simple good/bad split, these champions are above 50% in two regions and below it in one:\n${lines.join("\n")}\n\nThis is a descriptive split, not proof that a region caused the difference; sample size, matchups and regional meta can all contribute.`,
      evidence: lines,
      actions: [action("Compare region results", "/tier-list"), action("Open win rates", "/win-rates")],
      followUps: ["Why do regions have different results?", "How is Global calculated?"],
    };
  }
  if (/newbie|beginner|new player|just starting|easy champions?|who should i play/.test(q)) {
    const picks = context.site.beginnerRecommendations;
    if (!picks.length) return null;
    const lines = picks.map((entry) => `${entry.name} (${entry.role}) — difficulty ${entry.difficulty}/10, ${entry.tier} tier, ${entry.winRate.toFixed(1)}% WR`);
    return {
      source: "data",
      answer: `For a new player, I would start with a low-complexity champion and learn one role at a time. Good current starting points are:\n${lines.join("\n")}\n\nThese are data-informed starting points, not a promise that every matchup will be easy. Choose the role and champion whose kit you enjoy, then use the profile and Build Studio to learn the details.`,
      evidence: ["Recommendations prioritize difficulty 4/10 or lower, then current tier and win rate", ...lines.slice(0, 4)],
      actions: [action("Explore champions", "/champions"), action("Open tier list", "/tier-list")],
      followUps: ["Which beginner champion fits my role?", "What should I learn first on one of them?"],
    };
  }
  if (/best player.*(score|scored|calculated)|how.*best player/.test(q)) {
    return {
      source: "data",
      answer: "The Best Player score combines confidence-adjusted win rate, current rank, champion-leaderboard position, Champion Score and current-season games. This avoids naming someone #1 from a tiny lucky sample or from rank alone.",
      evidence: ["Current-season data", "Rank + board position + Champion Score + win rate + games"],
      actions: [action("Open global leaderboard", "/leaderboard")],
    };
  }
  if (/how.*win rate|where.*win rate|win rate.*calculated/.test(q)) {
    return {
      source: "data",
      answer: "WRTrueMeta collects current-season results from the top champion-leaderboard players in each supported region. Regional boards stay separate, and the Global view blends comparable regional samples instead of mixing them with unrelated public bracket statistics.",
      actions: [action("Open win rates", "/win-rates"), action("Open tier list", "/tier-list")],
    };
  }
  if (/what.*build studio|how.*build studio|what.*optimi[sz]/.test(q)) {
    return {
      source: "data",
      answer: "Build Studio combines the fight engine with model judgment. The engine compares measurable damage and durability across targets; the model handles practical effects, conditional passives and real-game tradeoffs. Full build generation keeps its own daily allowance—the site agent will send you there instead of secretly spending one.",
      actions: [action("Open Build Studio", "/build")],
    };
  }
  if (context.champion) {
    const answer = deterministicChampionAnswer(question, context.champion);
    if (answer) return answer;
  }
  return null;
}

export function agentSuggestions(pathname: string, championName?: string): string[] {
  if (championName) return [
    `How difficult is ${championName}?`,
    `Where does ${championName} rank?`,
    `What is ${championName}'s skill combo?`,
    `Who counters ${championName}?`,
  ];
  if (pathname.startsWith("/leaderboard")) return ["How is the Best Player score calculated?", "What makes the global leaderboard fair?"];
  if (pathname.startsWith("/build")) return ["What does Build Studio optimize?", "When should I use a counter build?"];
  if (pathname.startsWith("/tier-list") || pathname.startsWith("/win-rates")) return ["Why do regions have different results?", "Is the player pool 30 per region?", "What regions are currently tracked in the tier list?", "What data is available in the tier list?"];
  return ["How are win rates calculated?", "How is the Best Player score calculated?", "What does Build Studio optimize?"];
}

