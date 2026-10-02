# Rune and keystone engine validation — 2026-10-02

## Result

- Audited all **54** catalogue entries without Gemini or another model: **52
  current runes plus 2 removed entries retained for legacy saved builds**.
- **18** are fully modeled for the engine's synthetic champion-fight contract.
- **28** have useful numerical coverage but retain a disclosed context or match-history dependency.
- **8** are intentionally excluded because they are removed, require a takedown before their value begins, or affect only map/PvE play.
- **0** entries are silently unmodeled.
- The exhaustive Python/browser comparison passed **550 cases with 0 mismatches**.

The advisor now includes rune coverage in its authority decision. A partial
rune may still be measured and shown, but its score cannot trigger the
deterministic engine-win gate.

## Material corrections

- Patch 7.3 Lethal Tempo now ramps over six landed attacks and fires its
  melee/ranged adaptive max-stack bullets instead of granting stale permanent
  attack speed.
- Conqueror uses the 7.3 3–5 AD / 5–8.33 AP values and selects the adaptive
  stat rather than always granting AD.
- Grasp now deals damage from the user's max Health, heals from the user's max
  Health, applies the ranged modifier, and no longer scales from enemy Health.
- Cut Down applies only to the target's opening above-60%-Health slice.
- Last Stand is no longer silently worth zero; it uses a disclosed expected
  low-health uptime.
- Fleet Footwork includes its level, bonus-AD, and AP healing ratios.
- Chain Assault applies two marked hits; Tyrant checks the below-50% condition.
- Empowered Attack applies its ranged 80% modifier and adaptive damage type.
- Cheap Shot, Courage of the Colossus, and Ice Overlord require real hard CC,
  using the derived hard-CC detector rather than the noisy generic `cc` tag.
- Ice Overlord includes bonus-Health damage and a duration-limited resistance
  layer scaled from bonus Armor/MR.
- Battle Zeal and Empowerment ramp/arm during combat instead of starting at
  full strength at time zero.
- Second Wind uses 3 + 1.5% missing Health over five seconds, including the
  melee multiplier, rather than a stale flat 10 healing per second.
- Overgrowth includes 90 Health at 30 stacks plus the 3% max-Health threshold
  bonus. Further infinite farming remains contextual.
- Unshakeable uses the ordinary one-nearby-enemy 5% Armor/MR state rather than
  permanently assuming all three nearby enemies and 9%.
- Removed Legend: Tenacity and Ingenious Hunter are worth zero. Legend: Haste
  is present at its 15-haste maximum-stack value.
- Hubris is excluded from the no-prior-takedown reference fight instead of
  receiving Adaptive Force before its trigger.

## Deliberately contextual coverage

The largest remaining partials are not hidden bugs; they need inputs the
current request does not contain:

- game time or earlier farm/takedown progress (Gathering Storm, Manaflow,
  Legend stacks, Eyeball Collector, Zombie Ward, Grasp/Overgrowth history);
- current user/target Health and incoming hit timing (Last Stand, Absolute
  Focus, Bone Plating, Second Wind, Revitalize);
- positioning, ally targeting, summoner timing, or nearby-enemy count (Aery,
  Guardian, Nimbus Cloak, Unshakeable, Ice Overlord);
- exact ability-hit history and cooldown refund opportunities (Phase Rush,
  Transcendence, Arcane Comet).

The complete per-rune classification is in
`reports/rune_engine_coverage_full.json` and is reproducible with
`scripts/audit_rune_engine_coverage.py`.
