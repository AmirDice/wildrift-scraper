import cnData from "@/data/cn.json";
import { getChampion, type Champion } from "@/lib/data";

/** Which rank bracket to surface. "4" = 峡谷之巅 (Apex) — the highest rank. */
const BRACKET = "4";

interface CnEntry {
  winRate: number;
  pickRate: number;
  banRate: number;
  strength: number;
  position: string;
}
interface CnChamp {
  name: string;
  slug: string;
  heroId: string;
  cnName: string;
  byBracket: Record<string, CnEntry>;
}
const CN = cnData as unknown as {
  source: string;
  date: string;
  bracketLabels: Record<string, string>;
  champions: CnChamp[];
};

export const CN_META = {
  source: CN.source,
  date: CN.date,
  bracket: CN.bracketLabels[BRACKET],
};

/** CN win rates cluster near 50% (whole-ladder), so tiers use CN-specific cutoffs. */
function cnTier(wr: number): string {
  if (wr >= 53.5) return "GOD";
  if (wr >= 52) return "S";
  if (wr >= 50.8) return "A";
  if (wr >= 49.5) return "B";
  if (wr >= 48) return "C";
  return "Ass";
}

/** Champion object shaped like the EU one, plus CN pick/ban. Region-specific
 *  stats we don't have on CN (ceiling, games, mastery, best player) are nulled. */
export interface CnChampion extends Champion {
  cnPickRate: number;
  cnBanRate: number;
}

export function getCnChampions(): CnChampion[] {
  const out: CnChampion[] = [];
  for (const c of CN.champions) {
    const e = c.byBracket[BRACKET];
    const eu = getChampion(c.slug);
    if (!e || !eu) continue; // CN roster is a subset of EU; skip anything unmatched
    const tier = cnTier(e.winRate);
    out.push({
      ...eu,
      role: e.position,
      wr: e.winRate,
      tier,
      tierRole: tier,
      isOtp: false,
      meanWr: null,
      maxWr: null,
      winrateStd: null,
      medianGames: null,
      totalGames: null,
      nPlayers: null,
      medianMastery: null,
      maxScore: null,
      otpScore: null,
      topPlayer: null,
      skillSpread: null,
      bestPlayer: null,
      cnPickRate: e.pickRate,
      cnBanRate: e.banRate,
    });
  }
  return out.sort((a, b) => b.wr - a.wr);
}

export function cnRoles(): string[] {
  const order = ["Baron", "Jungle", "Mid", "Dragon", "Support"];
  const present = new Set(getCnChampions().map((c) => c.role));
  return order.filter((r) => present.has(r));
}

let _bySlug: Map<string, CnChampion> | null = null;
export function getCnBySlug(slug: string): CnChampion | undefined {
  if (!_bySlug) _bySlug = new Map(getCnChampions().map((c) => [c.slug, c]));
  return _bySlug.get(slug);
}
