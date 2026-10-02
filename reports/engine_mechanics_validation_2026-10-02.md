# Fight engine mechanics validation — 2026-10-02

## Scope

This report records the six-phase, model-free item mechanics pass. No Gemini or
other advisor-model request was made during validation.

## Final checks

- Python/TypeScript exhaustive parity: **550 cases, 0 mismatches**.
- TypeScript fight-behavior contracts: **58/58 passed**.
- Engine authority/trust contracts: **6/6 passed**.
- Python compilation: passed for the fight engine, build advisor, item audit,
  and trust-policy tests.
- Frontend TypeScript compilation: passed with `tsc --noEmit`.
- Item override JSON: parsed successfully.

## Completed-item passive coverage

The audit inspected 110 completed items that declare a passive or active:

- Fully modeled: **106**
- Explicitly partial: **3**
- Wholly unmodeled: **0**
- Stats-only by design: **1**

The explicitly partial items are:

1. **Ardent Censer** — holder buff and ally on-hit damage are modeled; the
   ally attack-speed increase is not converted because the synthetic fight
   does not know the ally's auto-attack damage share.
2. **Hexoptics C44** — distance-scaled attack damage is modeled in floor,
   expected, and ceiling bands; the post-takedown range window is outside the
   no-takedown reference fight.
3. **Shurelya's Battlesong** — active timing is modeled; ally movement-speed
   delivery value is not converted into guessed damage or survivability.

**Whispering Circlet** is the one stats-only entry. Its Harmony value is already
carried by the max-mana heal/shield-power stat rules, so it has no separate
combat-effect channel to add.

## Authority policy

The deterministic engine-win gate now checks both the engine challenger and
the best authored comparison build. A lead can auto-select the engine only
when all of the following are true:

- comparable scores and measurements exist;
- the engine lead is at least 5%;
- neither compared build has a build-relevant champion mechanic gap;
- neither compared build contains a declared partial/unmodeled item mechanic.

The local debug panel exposes the compared candidate IDs, margin result,
coverage result, trust level, and blocking limitations. Close or incomplete
comparisons remain advisory instead of being presented as authoritative.

## Deliberate scenario boundaries

- Ultimate haste is not valued as a second ultimate in an ordinary fight.
- Long item cooldowns such as Guardian Angel or Stasis are treated as at most
  one use in the simulated fight; cross-fight cooldown availability is not a
  score multiplier.
- Team follow-up after a revive, positioning, peel, post-takedown continuation,
  and ally movement/attack-speed conversion are not assigned invented numeric
  value. Where a compared item depends on one of these missing dimensions, the
  authority gate now discloses it and defers the verdict.

