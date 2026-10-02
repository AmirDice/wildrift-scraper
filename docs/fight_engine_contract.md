# Fight-engine simulation contract

The Python advisor engine and the browser TypeScript engine model one isolated
champion fight. They are build-comparison tools, not match simulators.

## Fight windows

- Three seconds represents burst/all-in output.
- Eight seconds represents a normal sustained fight.
- The 1v3 panel uses one primary target and at most two secondary targets. It
  measures damage coverage, not the probability of winning a literal 1v3.
- Reference targets may attack the simulated champion only where an explicit
  reactive mechanic needs that contact, such as Rammus reflection.

## Availability and cooldowns

- An ultimate can be cast at most once in any fight window.
- Ultimate haste never grants a second ultimate and has no numerical value in
  this one-fight model.
- A one-use effect that is ready when the fight begins may activate once.
- A cooldown matters only when it permits or prevents another activation inside
  the same fight. The engine does not penalize an effect because it may have
  been used in a previous fight.
- Basic-ability-only haste may change casts of slots 1-3. It must never affect
  the ultimate. Conversely, ultimate-only haste must never affect slots 1-3.

## Durability and context

- Guardian Angel is one 50%-max-Health second life. Its between-fight cooldown,
  team rescue, enemy repositioning and post-revive follow-up are not simulated.
- Team peel, ally rescue, positioning, objective timing and player intent are
  qualitative advisor considerations. They must not be converted into invented
  engine damage or durability.
- Persistent state from before the fight (for example Heartsteel stacks) must
  be supplied by an explicit scenario or a documented phase preset. It must not
  be inferred from the current fight.

## Parity requirement

The production advisor uses `web/fight_engine.py`. Browser diagnostics use
`web-next/src/lib/engine.ts`. Identical inputs must resolve identical stats,
casts, proc counts, damage channels, healing, shielding, reactive damage and
multi-target output. A feature is not complete until both implementations and
their parity/correctness fixtures pass.
