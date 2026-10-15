import loadoutData from "@/data/cn_loadouts.json";
import { getChampion, getChampions, type Champion } from "@/lib/data";

/**
 * Matchups, measured in China.
 *
 * These used to come from data/counters.json: a reviewed list of who beats
 * whom with a written reason and a confidence. It was opinion, however well
 * informed. The China loadout capture records, for every champion and lane,
 * the win rate against each opponent in Legendary ranked, so the matchups are
 * now that measurement.
 *
 * Only matchups played in at least MIN_PICK_RATE of the champion's games
 * count: below that a 70% can be a handful of games. "Strong" is a win rate
 * of at least STRONG_WR in the matchup and "weak" at most WEAK_WR, so a coin
 * flip is in neither list. A champion who appears in several lanes keeps the
 * most-played row for each opponent.
 */
export interface MatchupReference {
  slug: string;
  reason: string;
  /** 0-100: how far the matchup sits from even, for ranking and the compare page. */
  confidence?: number;
}

export interface ResolvedMatchup extends MatchupReference {
  champion: Champion;
  /** This champion's win rate in the matchup, in China Legendary ranked. */
  winRate: number;
  /** Share of this champion's games that are this matchup. */
  pickRate: number;
  lane: string;
}

type Row = { winRate: number; pickRate: number; entities: string[] };
type Lane = { lane: string; bracket: string; tabs: { versus?: { date: string | null; rows: Row[] } } };
const DATA = (loadoutData as unknown as { champions: Record<string, Lane[]> }).champions;

const MIN_PICK_RATE = 1;
const STRONG_WR = 51;
const WEAK_WR = 49;

const LANE_NAME: Record<string, string> = {
  baron: "Baron lane", jungle: "jungle", mid: "mid lane", dragon: "Dragon lane", support: "support",
};
const BRACKET_NAME: Record<string, string> = { legendary: "Legendary", challenger: "Challenger" };

let BY_NAME: Map<string, Champion> | null = null;
function championByName(name: string): Champion | undefined {
  BY_NAME ??= new Map(getChampions().map((champion) => [champion.name, champion]));
  return BY_NAME.get(name);
}

/** Every measured opponent for a champion, most-played row per opponent. */
function measured(slug: string): ResolvedMatchup[] {
  const self = getChampion(slug);
  if (!self) return [];
  const best = new Map<string, ResolvedMatchup>();
  for (const lane of DATA[slug] ?? []) {
    for (const row of lane.tabs.versus?.rows ?? []) {
      if (row.entities.length !== 1 || row.pickRate < MIN_PICK_RATE) continue;
      const champion = championByName(row.entities[0]);
      if (!champion || champion.slug === slug) continue;
      const previous = best.get(champion.slug);
      if (previous && previous.pickRate >= row.pickRate) continue;
      const where = `China ${BRACKET_NAME[lane.bracket] ?? lane.bracket} ${LANE_NAME[lane.lane] ?? lane.lane}`;
      best.set(champion.slug, {
        slug: champion.slug,
        champion,
        winRate: row.winRate,
        pickRate: row.pickRate,
        lane: lane.lane,
        confidence: Math.min(100, Math.round(Math.abs(row.winRate - 50) * 8)),
        reason: `${self.name} wins ${row.winRate.toFixed(1)}% of ${where} games against ${champion.name}, `
          + `a matchup in ${row.pickRate.toFixed(1)}% of ${self.name}'s games there.`,
      });
    }
  }
  return [...best.values()];
}

/** Champions this champion is strong / weak against, strongest edge first. */
export function getMatchups(slug: string): { strong: ResolvedMatchup[]; weak: ResolvedMatchup[] } {
  const rows = measured(slug);
  return {
    strong: rows.filter((row) => row.winRate >= STRONG_WR).sort((a, b) => b.winRate - a.winRate),
    weak: rows.filter((row) => row.winRate <= WEAK_WR).sort((a, b) => a.winRate - b.winRate),
  };
}

/** When the matchups were captured, for the page caption. */
export function matchupsCapturedOn(slug: string): string | null {
  const dates = (DATA[slug] ?? []).map((lane) => lane.tabs.versus?.date).filter((date): date is string => Boolean(date));
  return dates.sort().at(-1) ?? null;
}

/**
 * Every champion's matchups in the shape the compare page reads.
 *
 * The compare page ships this to the browser, so it keeps each champion's
 * `limit` sharpest edges each way with a short reason: the full table with
 * page-length reasons was 686 KB against the old file's 242 KB.
 */
export function matchupTable(limit = 8): Record<string, { strong: MatchupReference[]; weak: MatchupReference[] }> {
  return Object.fromEntries(getChampions().map((self) => {
    // Names both sides: the compare page shows this under whichever champion
    // wins, so "25.0% against Shen" read as Shen's number on Riven vs Shen.
    const strip = ({ slug, champion, winRate, confidence }: ResolvedMatchup): MatchupReference => ({
      slug, confidence, reason: `${self.name} wins ${winRate.toFixed(1)}% of games against ${champion.name} in China.`,
    });
    const { strong, weak } = getMatchups(self.slug);
    return [self.slug, { strong: strong.slice(0, limit).map(strip), weak: weak.slice(0, limit).map(strip) }];
  }));
}
