# Best Player and Global Leaderboard redesign

Status: design only. No scraper run or production data change is part of this document.

## Goals

1. Show a meaningful top-three podium for every champion.
2. Make the champion podium work across EU, NA, and CN once the current collection has player-level rows for all three servers.
3. Expose a comparable global rank without pretending that raw server ranks, LP, or Champion Score are interchangeable.
4. Keep the current-season title separate from a player's long-term career record.
5. Preserve the current small-sample protection and make the new score explainable in the UI.

## What exists today

The current Best Player pipeline:

- limits the candidate pool to the top 50 champion-board rows;
- applies an adaptive minimum-games floor;
- computes a 95% Wilson lower-bound win rate from the player's current win rate and games;
- excludes names that are not eligible for a title;
- crowns one player by the highest Wilson lower bound.

Tier, champion-board position, and Champion Score are available as row metadata, but they are not components of the current crown score. Games influence the result through the Wilson calculation and entry floor, not as an independent linear bonus.

## Concepts and scopes

There are two different rankings and they must not be conflated:

### Champion podium

The best current-season players on one champion. Candidates are individual champion-board rows. A player may appear on several champion podiums.

### Global leaderboard

A cross-server view of champion-board entries, with a server badge on every row. It uses server-normalized metrics and a versioned score. It is not a sum of raw EU, NA, and CN ranks.

The initial global view should be champion-scoped (for example, Global Rammus). A later all-champions player leaderboard can aggregate a player's champion entries, but that is a separate product and should not be silently mixed into the champion podium.

## Candidate record

Every collected champion-board row should normalize into this shape before scoring:

```ts
type PlayerChampionEntry = {
  server: "EU" | "NA" | "CN";
  championSlug: string;
  playerId: string | null;       // preferred; display name is not identity
  playerName: string;
  championRank: number;
  tier: string | null;
  tierPoints: number | null;     // LP/score when the server exposes it
  championScore: number | null;
  games: number | null;
  wins: number | null;
  winRate: number | null;
  capturedAt: string;
  patch: string | null;
  season: string | null;
  source: "in_game" | "api" | "import";
};
```

`playerId` is important for a true global view. If a server does not expose a stable ID, keep the display name and server as the identity and do not merge similarly named accounts across servers.

## Current-season score v1

The score is 0–100 and is calculated only after eligibility checks. The recommended weights are:

| Component | Weight | Treatment |
|---|---:|---|
| Confidence-adjusted win rate | 45% | Wilson lower bound (or an equivalent empirical-Bayes lower estimate), normalized within the champion candidate pool |
| Ladder strength | 20% | Tier plus exact points when available; map to a server-normalized percentile |
| Champion-board position | 20% | `1 - (championRank - 1) / (candidateDepth - 1)` |
| Champion Score/mastery | 10% | Log/percentile normalized within server and champion; never raw-linear |
| Current-season games | 5% | Capped/logarithmic experience signal; the Wilson term already handles sample reliability |

This deliberately prevents a high-volume grinder from winning on games alone. Ladder strength and champion-board position are correlated, so their combined weight should stay at or below 40%.

### Eligibility

- Current season and current patch window only.
- Top `candidateDepth` rows (the collection depth is configuration, not a hardcoded UI assumption).
- The existing adaptive games floor remains in force.
- Title-integrity filtering remains in force.
- Missing metrics are not converted to zero. The score records a coverage flag and renormalizes only if the missing field is genuinely unavailable.

### Tie-breakers

1. Higher confidence-adjusted win rate.
2. Higher ladder-strength percentile.
3. Higher champion-board position.
4. More current-season games, capped at the reliability ceiling.

Every output stores `scoringVersion: "best-player-v1"` so a future formula change does not silently rewrite historical pages.

## Cross-server normalization

EU, NA, and CN must be normalized independently before a global comparison:

- Do not compare raw LP or Champion Score values across servers.
- Use tier/points percentiles within each server's current capture.
- Normalize Champion Score and games by server/champion distributions.
- Keep the original values visible beside the normalized score.
- Mark stale or missing server rows instead of filling them with zero.

The global champion podium is valid only when the collection manifest confirms player-level rows for the participating servers. CN's current aggregate champion data cannot produce a player podium; the new CN collection must replace that aggregate limitation for this feature.

## Export contract

Each champion should eventually export:

```json
{
  "bestPlayer": { "...": "backwards-compatible winner summary" },
  "bestPlayerPodium": {
    "scoringVersion": "best-player-v1",
    "scope": "global",
    "capturedAt": "...",
    "players": [
      {
        "player": "...",
        "server": "EU",
        "championRank": 1,
        "tier": "Challenger",
        "championScore": 12345,
        "games": 86,
        "winRate": 67.4,
        "confidenceWr": 58.9,
        "score": 91.2,
        "coverage": { "tier": true, "score": true, "games": true }
      }
    ]
  }
}
```

The legacy `bestPlayer` field remains during migration so existing champion pages and cached builds do not break. New consumers should use `bestPlayerPodium`.

## UI direction

### Leaderboard page

- Tabs: Global, EU, NA, CN.
- Champion selector remains the primary control.
- Put the three-player podium above the full table.
- Each podium card shows player name, server flag, tier, champion rank, current win rate, games, Champion Score, and the composite score.
- A compact “Why this ranking?” popover explains the five weights and links to methodology.
- The full table keeps sortable raw columns and adds `Best Score` and `Server`.
- Show collection timestamp, patch, season, and a “CN player rows collected” status.

### Champion page

- Add a compact “Top 3 players this season” block near the current Best Player spotlight.
- Keep the current winner treatment for rank 1, but make rank 2 and rank 3 visible without scrolling through the full table.
- Include a link to the champion-filtered global leaderboard.

### Confidence and honesty

Use explicit labels such as “Current season” and “Global candidate pool.” Never call a CN aggregate champion row a player ranking.

## All-time data

All-time champion games and win rate are not currently present in the Best Player input. The current `games`, `winrate`, and `captured_at` values are collection-period values; mastery/Champion Score is not an all-time win-rate record.

When lifetime champion history becomes available, keep it in a separate `careerRecord` object:

```ts
type CareerRecord = {
  games: number;
  wins: number;
  winRate: number;
  seasons: number;
  lastUpdated: string;
};
```

Do not mix it into the current-season crown. Patch and season changes make old performance non-comparable. Display it as a “Career record” badge or secondary panel. At most, it may be used as a final tie-breaker when current scores are effectively equal and both players clear the current-season sample floor; it should never outweigh current-season performance.

## Rollout sequence

1. Finish the EU/NA/CN player-level collection and publish a manifest with server, patch, season, depth, and capture time.
2. Add the normalized entry schema and pure scoring functions with fixture tests for small samples, missing fields, and cross-server normalization.
3. Export `bestPlayerPodium` while retaining the legacy `bestPlayer` field.
4. Add Global/EU/NA/CN podium controls and the methodology popover.
5. Compare the v1 podium against the current Wilson-only winner and review edge cases before making v1 the default crown.
6. Add career records later as a separate feature, not as part of this migration.

## Acceptance criteria

- A champion can show three eligible players from a mixed EU/NA/CN pool.
- The same raw player row produces the same score regardless of UI sort order.
- A 100% win rate from a tiny sample cannot beat a materially stronger high-volume player solely because of raw win rate.
- A large games total cannot dominate the score by itself.
- EU, NA, and CN raw values remain visible and traceable to their source.
- Missing CN player-level data produces an explicit unavailable state, never a fabricated global podium.
- Changing `scoringVersion` leaves prior exported results auditable.
