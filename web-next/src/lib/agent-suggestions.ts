/**
 * The questions the site agent suggests, in one place.
 *
 * They used to live in three copies -- the widget, the champion page chips and
 * agent-context.ts -- and only the last was ever edited, so the chips went on
 * offering "How difficult is X?" and "What is X's skill combo?" after both had
 * been rewritten. This module imports no data, so the client widget can use
 * it without pulling the agent's server-side data into the browser bundle.
 *
 * Every question here is one the fast path in agent-context.ts answers from
 * site data. A suggestion that falls through to the model spends an anonymous
 * visitor's single AI answer for the day on a click they did not think about.
 */

export function championPrompts(name: string): string[] {
  return [
    `What runes do top players use on ${name}?`,
    `Who counters ${name}?`,
    `What is ${name}'s skill order?`,
    `What changed for ${name} recently?`,
  ];
}

export function agentSuggestions(pathname: string, championName?: string): string[] {
  if (championName) return championPrompts(championName);
  if (pathname.startsWith("/leaderboard")) return ["How is the Best Player score calculated?", "Is the player pool 30 per region?"];
  if (pathname.startsWith("/build")) return ["What does Build Studio optimize?", "What items are good against healing?"];
  if (pathname.startsWith("/items")) return ["What items are good against healing?", "What does Essence Reaver do?"];
  if (pathname.startsWith("/tier-list") || pathname.startsWith("/win-rates")) return [
    "Who is the best jungler right now?",
    "What does GOD tier mean?",
    "Why do regions have different results?",
    "Is the player pool 30 per region?",
  ];
  if (pathname.startsWith("/champion-changes") || pathname.startsWith("/updates") || pathname.startsWith("/movers")) return [
    "What changed in the latest patch?",
    "How often is the tier list updated?",
  ];
  return ["What changed in the latest patch?", "Who is the strongest ADC right now?", "What champion should I play as a new player?"];
}
