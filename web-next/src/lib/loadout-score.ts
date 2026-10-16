/**
 * Which loadout row to recommend: the best balance of win rate and how often
 * it is played.
 *
 * The highest win rate in a tab is usually a small sample: Riven's top Baron
 * core by win rate was 66.7% over 1.6% of games, while her main core held
 * 59.8% over 18%. Each row's win rate is pulled toward the tab's average,
 * harder the less it is played (the same shrinkage the tier list applies to
 * champions), and the highest adjusted row with a real sample is recommended.
 *
 * PRIOR is the pull, in pick-rate points: a row played PRIOR% of the time is
 * weighted half its own rate, half the average. Tuned on all 502 tabs of the
 * Oct 15 capture: at 15 the recommended row is played in a median 10% of
 * games, is the most-played row a third of the time, and is otherwise a
 * well-sampled row that genuinely outperforms it. Weaker pulls let rare rows
 * tie with main cores (Jinx's 2.2% core tied her 23.6% one at 5).
 *
 * The data gives pick rate as a share of the champion's games, not a game
 * count, so 2% on a popular champion and 2% on a rare one are treated alike.
 */
export const PRIOR = 15;
/** No recommendation from a row played less than this share of games. */
export const RECOMMEND_MIN_PICK = 3;

type Scored = { winRate: number; pickRate: number };

/** The tab's average win rate, weighted by how often each row is played. */
export function tabAverage(rows: Scored[]): number | null {
  const total = rows.reduce((sum, row) => sum + row.pickRate, 0);
  if (!total) return null;
  return rows.reduce((sum, row) => sum + row.winRate * row.pickRate, 0) / total;
}

/** A row's win rate after the pull toward the tab average. */
export function adjustedWinRate(row: Scored, average: number): number {
  return (row.winRate * row.pickRate + average * PRIOR) / (row.pickRate + PRIOR);
}

/** The row to recommend, or null when nothing has a big enough sample. */
export function recommendedRow<T extends Scored>(rows: T[]): T | null {
  const average = tabAverage(rows);
  if (average == null) return null;
  let best: T | null = null;
  let bestScore = -Infinity;
  for (const row of rows) {
    if (row.pickRate < RECOMMEND_MIN_PICK) continue;
    const score = adjustedWinRate(row, average);
    if (score > bestScore) { best = row; bestScore = score; }
  }
  return best;
}

/** Rows ordered best first by adjusted win rate. */
export function rankByBalance<T extends Scored>(rows: T[]): T[] {
  const average = tabAverage(rows);
  if (average == null) return rows;
  return [...rows].sort((a, b) => adjustedWinRate(b, average) - adjustedWinRate(a, average));
}
