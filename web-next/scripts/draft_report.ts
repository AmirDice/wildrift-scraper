/**
 * Drive the Draft Assistant's own logic over a set of realistic ranked games
 * and dump what it would show, as JSON.
 *
 * This imports the SAME modules the page renders from -- lib/draft.ts for the
 * pick and ban ranking, lib/threat.ts for the enemy read and the engine-scored
 * swaps -- so the report is what the tool actually says, not a description of
 * what it ought to say.
 *
 *     npx tsx scripts/draft_report.ts > ../reports/draft_report.json
 */
import { getChampions, type Champion } from "../src/lib/data";
import { getBuildsFor, visibleBuildVariants } from "../src/lib/builds";
import { counterSwaps, roster, threatProfile, recommendCounters } from "../src/lib/threat";
import { buildEnemyTraits, emptyDraft, normaliseDraft, picked, suggestBans, suggestPicks, unavailable,
  type DraftState, type DraftRole } from "../src/lib/draft";

interface Scenario {
  id: string;
  champion: string;      // the pool champion this game is about
  role: DraftRole;
  mainRole: DraftRole;
  label: string;         // what the enemy comp is, in words
  bans: string[];
  allies: string[];
  enemies: string[];
}

const POOL_NAMES = ["Graves", "Hecarim", "Xin Zhao", "Pantheon", "Ekko", "Olaf",
  "Lucian", "Vayne", "Leona", "Garen", "Nami", "Gwen", "Diana"];

// Thirteen games, one per pool champion, each a different problem to solve.
// Bans are ten deep and include a duplicate where both teams targeted the same
// champion, which is what a real lobby looks like.
const SCENARIOS: Scenario[] = [
  {
    id: "graves", champion: "Graves", role: "Jungle", mainRole: "Jungle",
    label: "Poke and disengage: they win from range and refuse the fight",
    bans: ["Nilah", "Nilah", "Hecarim", "Yone", "Zed", "Kayn", "Fiora", "Vayne", "Akali", "Master Yi"],
    allies: ["Garen", "Orianna", "Caitlyn", "Braum"],
    enemies: ["Jayce", "Nidalee", "Ziggs", "Varus", "Janna"],
  },
  {
    id: "hecarim", champion: "Hecarim", role: "Jungle", mainRole: "Jungle",
    label: "Wall of crowd control: every one of them can lock you down",
    bans: ["Nilah", "Yone", "Nidalee", "Kayn", "Ekko", "Ekko", "Fiora", "Akali", "Vayne", "Zed"],
    allies: ["Camille", "Ahri", "Jinx", "Nami"],
    enemies: ["Malphite", "Amumu", "Lissandra", "Ashe", "Leona"],
  },
  {
    id: "xin-zhao", champion: "Xin Zhao", role: "Jungle", mainRole: "Jungle",
    label: "Health bars everywhere: a frontline in four of the five seats",
    bans: ["Nilah", "Hecarim", "Nidalee", "Yone", "Master Yi", "Kayn", "Akali", "Akali", "Zed", "Fiora"],
    allies: ["Gwen", "Syndra", "Jhin", "Lulu"],
    enemies: ["Ornn", "Rammus", "Galio", "Kog'Maw", "Braum"],
  },
  {
    id: "pantheon", champion: "Pantheon", role: "Jungle", mainRole: "Jungle",
    label: "Glass everywhere: whoever lands the first spell wins the fight",
    bans: ["Nilah", "Hecarim", "Malphite", "Leona", "Nautilus", "Amumu", "Ornn", "Ornn", "Sett", "Maokai"],
    allies: ["Garen", "Orianna", "Samira", "Braum"],
    enemies: ["Gwen", "Evelynn", "Lux", "Jinx", "Sona"],
  },
  {
    id: "ekko", champion: "Ekko", role: "Jungle", mainRole: "Jungle",
    label: "Physical dive: all five deal AD and three of them jump on you",
    bans: ["Nilah", "Yone", "Fiora", "Gwen", "Akali", "Katarina", "Kayn", "Nidalee", "Nidalee", "Vladimir"],
    allies: ["Malphite", "Orianna", "Caitlyn", "Nami"],
    enemies: ["Darius", "Master Yi", "Zed", "Samira", "Pyke"],
  },
  {
    id: "olaf", champion: "Olaf", role: "Baron", mainRole: "Baron",
    label: "Sustain and shields: they heal through everything you do",
    bans: ["Nilah", "Hecarim", "Yone", "Zed", "Kayn", "Fiora", "Fiora", "Master Yi", "Akali", "Nidalee"],
    allies: ["Xin Zhao", "Ahri", "Jinx", "Leona"],
    enemies: ["Aatrox", "Warwick", "Vladimir", "Kog'Maw", "Soraka"],
  },
  {
    id: "garen", champion: "Garen", role: "Baron", mainRole: "Baron",
    label: "Magic damage from every seat on their team",
    bans: ["Nilah", "Hecarim", "Yone", "Zed", "Master Yi", "Kayn", "Vayne", "Vayne", "Fiora", "Samira"],
    allies: ["Graves", "Lucian", "Orianna", "Braum"],
    enemies: ["Mordekaiser", "Diana", "Syndra", "Kai'Sa", "Seraphine"],
  },
  {
    id: "lucian", champion: "Lucian", role: "Dragon", mainRole: "Dragon",
    label: "Assassins hunting the backline, and you are the backline",
    bans: ["Nilah", "Hecarim", "Malphite", "Ornn", "Sion", "Maokai", "Amumu", "Amumu", "Sett", "Braum"],
    allies: ["Garen", "Xin Zhao", "Orianna", "Leona"],
    enemies: ["Camille", "Kha'Zix", "Zed", "Samira", "Pyke"],
  },
  {
    id: "vayne", champion: "Vayne", role: "Dragon", mainRole: "Dragon",
    label: "Unkillable: four tanks and a frontline support",
    bans: ["Nilah", "Hecarim", "Zed", "Katarina", "Fizz", "Akali", "Kayn", "Kayn", "Yone", "Master Yi"],
    allies: ["Gwen", "Xin Zhao", "Orianna", "Nami"],
    enemies: ["Ornn", "Rammus", "Galio", "Sivir", "Alistar"],
  },
  {
    id: "leona", champion: "Leona", role: "Support", mainRole: "Support",
    label: "Poke and disengage: they never let you reach them",
    bans: ["Nilah", "Hecarim", "Yone", "Zed", "Kayn", "Fiora", "Master Yi", "Akali", "Akali", "Vayne"],
    allies: ["Garen", "Xin Zhao", "Ahri", "Lucian"],
    enemies: ["Jayce", "Nidalee", "Ziggs", "Ezreal", "Janna"],
  },
  {
    id: "nami", champion: "Nami", role: "Support", mainRole: "Support",
    label: "Hard engage: one hook or one ultimate ends the fight",
    bans: ["Nilah", "Hecarim", "Yone", "Zed", "Master Yi", "Kayn", "Fiora", "Akali", "Vayne", "Vayne"],
    allies: ["Garen", "Xin Zhao", "Orianna", "Lucian"],
    enemies: ["Malphite", "Amumu", "Yasuo", "Miss Fortune", "Blitzcrank"],
  },
  {
    // Four durable bodies. The question is whether a champion whose damage
    // scales with the target's health is told to lean on that, and whether a
    // magic-damage Baron laner is given the right resistance against a comp
    // whose damage is nearly all physical.
    id: "gwen", champion: "Gwen", role: "Baron", mainRole: "Baron",
    label: "A wall of health: four durable bodies and nothing to burst",
    bans: ["Nilah", "Nilah", "Yone", "Fiora", "Camille", "Sett", "Akali", "Zed", "Kayn", "Master Yi"],
    allies: ["Xin Zhao", "Orianna", "Caitlyn", "Nami"],
    enemies: ["Malphite", "Rammus", "Galio", "Ashe", "Leona"],
  },
  {
    // Everything on this team shields something. A burst diver who cannot get
    // through a shield does not get to the kill, so this asks whether shield
    // reduction is reached for and whether an AP diver is kept off bruiser
    // items against a squishy back line.
    id: "diana", champion: "Diana", role: "Jungle", mainRole: "Jungle",
    label: "Shields on everything: the burst lands and the health bar refills",
    bans: ["Yone", "Yone", "Nilah", "Nidalee", "Kayn", "Akali", "Zed", "Fiora", "Master Yi", "Camille"],
    allies: ["Sion", "Ahri", "Jinx", "Braum"],
    enemies: ["Jayce", "Lee Sin", "Orianna", "Varus", "Janna"],
  },
];

function slugOf(champions: Champion[], name: string): string {
  const c = champions.find((x) => x.name === name);
  if (!c) throw new Error(`unknown champion in scenario: ${name}`);
  return c.slug;
}

function validate(sc: Scenario, champions: Champion[]): void {
  const roleOf = new Map(champions.map((c) => [c.name, c.role]));
  const banned = new Set(sc.bans);
  for (const name of [...sc.allies, ...sc.enemies, sc.champion]) {
    if (banned.has(name)) throw new Error(`${sc.id}: ${name} is banned and also picked`);
  }
  const picked = [...sc.allies, ...sc.enemies, sc.champion];
  const twice = picked.filter((n, i) => picked.indexOf(n) !== i);
  if (twice.length) throw new Error(`${sc.id}: ${twice.join(", ")} picked on both teams`);
  for (const [side, names] of [["your team", [...sc.allies, sc.champion]],
                               ["enemy team", sc.enemies]] as [string, string[]][]) {
    const roles = names.map((n) => roleOf.get(n));
    const missing = ["Baron", "Jungle", "Mid", "Dragon", "Support"]
      .filter((r) => !roles.includes(r));
    if (missing.length) {
      throw new Error(`${sc.id}: ${side} has no ${missing.join("/")} (roles: ${roles.join(", ")})`);
    }
  }
}

function main() {
  const champions = getChampions();
  const bySlug = new Map(champions.map((c) => [c.slug, c]));
  const pool = POOL_NAMES.map((n) => slugOf(champions, n));
  const R = roster();

  SCENARIOS.forEach((sc) => validate(sc, champions));

  const out = SCENARIOS.map((sc) => {
    // The scenarios list champions, the board holds seats: normaliseDraft is
    // the one place that turns one into the other.
    const state: DraftState = normaliseDraft({
      bans: sc.bans.map((n) => slugOf(champions, n)),
      allies: sc.allies.map((n) => slugOf(champions, n)),
      enemies: sc.enemies.map((n) => slugOf(champions, n)),
      me: null,
      myRole: sc.role,
    });
    // One builder, shared with the draft page, so a trait added for one
    // cannot go missing from the other.
    const enemyTraits = buildEnemyTraits(picked(state.enemies), Object.values(R), bySlug);

    // Ban phase first: what the tool would have told them to ban, given a
    // clean slate but the same pool and role.
    const banAdvice = suggestBans(
      { ...emptyDraft(), myRole: sc.role }, pool, champions, 5);

    const poolPicks = suggestPicks(state, pool, champions, bySlug, 6, enemyTraits);
    const overallPicks = suggestPicks(state, [], champions, bySlug, 6, enemyTraits)
      .filter((s) => !pool.includes(s.champion.slug));

    const profile = threatProfile(sc.enemies, 13, sc.role);
    const recs = profile ? recommendCounters(profile) : [];

    // The build the page would show for THIS champion, and the free swaps it
    // measures against this comp.
    const cb = getBuildsFor(sc.champion);
    const variant = cb ? visibleBuildVariants(cb)[0] : undefined;
    const build = cb && variant ? cb.builds[variant] : null;
    const items = (build?.coreBuild ?? []).map((i) => i.slug).filter(Boolean);
    const runeNames = [build?.runes?.keystone?.name,
      ...(build?.runes?.treeMinors ?? []).map((r) => r.name)].filter(Boolean) as string[];
    const swaps = profile && items.length
      ? counterSwaps(sc.champion, items, runeNames, profile, 15, items.slice(0, 1))
      : [];

    const gone = unavailable(state);
    return {
      id: sc.id,
      label: sc.label,
      champion: sc.champion,
      role: sc.role,
      mainRole: sc.mainRole,
      filled: sc.role !== sc.mainRole,
      bans: sc.bans,
      banDuplicates: sc.bans.filter((b, i) => sc.bans.indexOf(b) !== i),
      allies: sc.allies,
      enemies: sc.enemies,
      unavailableCount: gone.size,
      bannedSuggestionLeak: [...poolPicks, ...overallPicks]
        .filter((s) => gone.has(s.champion.slug)).map((s) => s.champion.name),
      banAdvice: banAdvice.map((s) => ({
        name: s.champion.name, tier: s.champion.tier, wr: s.champion.wr, why: s.reasons,
      })),
      poolPicks: poolPicks.map((s) => ({
        name: s.champion.name, tier: s.champion.tier, wr: s.champion.wr,
        score: Math.round(s.score * 100) / 100, offRole: s.offRole, why: s.reasons,
      })),
      overallPicks: overallPicks.map((s) => ({
        name: s.champion.name, tier: s.champion.tier, wr: s.champion.wr,
        score: Math.round(s.score * 100) / 100, why: s.reasons,
      })),
      enemyRead: profile ? {
        physicalPct: Math.round(profile.adShare * 100),
        magicPct: Math.round(profile.apShare * 100),
        laneOpponent: profile.laneOpponent,
        healers: profile.healers, shielders: profile.shielders,
        assassins: profile.assassins, marksmen: profile.marksmen,
        ccCount: profile.ccCount,
        frontlineTarget: profile.frontline, carryTarget: profile.carry,
      } : null,
      counterPriorities: recs.map((r) => ({ label: r.label, reason: r.reason,
        severity: Math.round(r.severity * 100) / 100 })),
      standardBuild: {
        variant: variant ?? null,
        items: (build?.coreBuild ?? []).map((i) => i.name),
        boots: build?.boots?.name ?? null,
        upgrade: build?.enchantment?.name ?? null,
        keystone: build?.runes?.keystone?.name ?? null,
        minors: (build?.runes?.treeMinors ?? []).map((r) => r.name),
        summoners: (build?.summoners ?? []).map((s) => s.name),
      },
      freeSwaps: swaps.filter((s) => s.swap).map((s) => ({
        add: s.swap!.add, remove: s.swap!.remove, delta: s.swap!.delta, reason: s.reason,
      })),
    };
  });

  process.stdout.write(JSON.stringify({ pool: POOL_NAMES, games: out }, null, 2));
}

main();
