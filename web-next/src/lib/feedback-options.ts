/** Reason chips offered with build feedback. Shared by the API (which only
 *  accepts these keys, so they aggregate) and the UI (which renders them). */
export const FEEDBACK_REASONS = [
  { key: "spot-on", label: "Spot on", verdict: "up" },
  { key: "learned-something", label: "Taught me something", verdict: "up" },
  { key: "matches-my-build", label: "Matches what I build", verdict: "up" },
  { key: "items-wrong", label: "Wrong items", verdict: "down" },
  { key: "runes-wrong", label: "Wrong runes", verdict: "down" },
  { key: "not-my-playstyle", label: "Not my playstyle", verdict: "down" },
  { key: "ignores-enemies", label: "Ignores the enemy team", verdict: "down" },
  { key: "explanation-unclear", label: "Explanation unclear", verdict: "down" },
] as const;

export type FeedbackVerdict = "up" | "down";

export const FEEDBACK_REASON_KEYS = FEEDBACK_REASONS.map((reason) => reason.key);

export function reasonsFor(verdict: FeedbackVerdict) {
  return FEEDBACK_REASONS.filter((reason) => reason.verdict === verdict);
}
