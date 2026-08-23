import data from "@/data/tier_explanations.json";

/**
 * Per-champion "what the numbers say", written by the model from that
 * champion's own measurements and nothing else.
 *
 * Generated offline by scripts/generate_tier_explanations.py, not at request
 * time: the text only changes when the data does, so paying for a generation
 * per page view would buy nothing. Every number in the text was checked
 * against the champion's fact sheet before it was written here, and the
 * generator refuses to explain the KIT -- it was never given one.
 *
 * A champion missing from the file simply has no paragraph yet (a new
 * champion, or a generation that failed validation). Callers render nothing
 * rather than a placeholder.
 */
interface Explanation {
  text: string;
  /** The tier the text was written against, so a stale paragraph is detectable. */
  tier: string;
  wr: number;
}

const FILE = data as unknown as {
  generatedAt: string;
  model: string;
  champions: Record<string, Explanation>;
};

export const EXPLANATIONS_GENERATED_AT = FILE.generatedAt;

/** The paragraph for a champion, or null. `currentTier` guards against text
 *  written before a data refresh moved the champion: a paragraph that opens
 *  "jumped to GOD tier" is wrong once the champion is back in S, and stale is
 *  worse than absent here. */
export function getExplanation(slug: string, currentTier?: string): string | null {
  const entry = FILE.champions[slug];
  if (!entry) return null;
  if (currentTier && entry.tier && entry.tier !== currentTier) return null;
  return entry.text || null;
}
