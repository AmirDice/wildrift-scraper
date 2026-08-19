"use client";

import { useMemo } from "react";
import { duel, dummyTarget, resolveStats, rotation } from "@/lib/engine";
import { blockedItems, hasSimulatableKit } from "@/lib/customizer-data";
import engineData from "@/data/engine.json";

/* eslint-disable @next/next/no-img-element */

const DATA = engineData as {
  items?: Record<string, { name?: string; icon?: string; cost?: number; category?: string }>;
  formulas?: Record<string, { mechanics?: { kind?: string }[] }>;
  champions?: Record<string, { damageMetric?: string }>;
};

/** Burst window, matching the engine's burst3: what a mage or assassin is
 *  judged on, where a bruiser or marksman is judged at second eight. */
const BURST_WINDOW = 3;

/** Which axis this champion is measured on, precomputed in Python so both
 *  engines agree. Ranking a burst mage on sustained damage is what made
 *  attack-speed items look strong on casters. */
function metricOf(name: string): "burst" | "sustained" | "durability" {
  const m = DATA.champions?.[name]?.damageMetric;
  return m === "burst" || m === "durability" ? m : "sustained";
}

const itemIcon = (slug: string) => DATA.items?.[slug]?.icon ?? `/items/${slug}.webp`;
const itemName = (slug: string) => DATA.items?.[slug]?.name ?? slug;

/**
 * The build as it is actually experienced: one item, two items, three, full --
 * because most Wild Rift games end long before six.
 *
 * Every number here is the ENGINE's, not the model's: for each purchase stage
 * the champion's stats are resolved with that prefix of the build and run
 * against a reference dummy (3,000 HP, 60 armor, 45 MR -- a mid-game bruiser
 * profile), so the damage curve and the health curve are the same maths the
 * Custom Lab's fight uses. The "strongest spike" is the stage with the biggest
 * marginal DPS jump per gold-equivalent slot, which is the honest version of
 * "when is this build scariest".
 *
 * Boots are inserted where the strip shows them landing (after the second
 * item), so the stages mirror the purchase order the player was just shown.
 */
export function BuildStages({ name, items, boots, bootsUpgrade, bootsUpgradeAfter, runeNames, level = 15, bare = false, powerCurve, candidates }: {
  name: string;
  items: string[];
  boots?: string;
  bootsUpgrade?: string;
  /** Model-chosen upgrade timing: tier-3 lands after this many completed
   *  items; 0 = stays tier-2 all game. Absent on older builds (reads as 2). */
  bootsUpgradeAfter?: number;
  runeNames: string[];
  level?: number;
  /** Renders without its own card chrome, for embedding inside "Your Build". */
  bare?: boolean;
  /** The request's power-curve goal ("early" | "balanced" | ...). The
   *  substitution check only runs for an EARLY goal: trading late power for
   *  an earlier spike is exactly what that goal asks for, and exactly what
   *  it would be wrong to suggest under any other goal. */
  powerCurve?: string;
  /** The model's scored item alternatives, the substitution candidate pool. */
  candidates?: { item: string; score?: number }[];
}) {
  const stages = useMemo(() => {
    if (!items.length || !hasSimulatableKit(name)) return null;
    // Only the base form is modelled for transformers; skip rather than lie.
    if ((DATA.formulas?.[name]?.mechanics ?? []).some((m) => m.kind === "transform")) return null;

    // EVERY purchase is its own measured step -- items, the tier-2 boots,
    // and the tier-3 enchant separately. Bundling boots into an item stage
    // handed that stage two purchases' worth of gain and the spike badge
    // followed the boots rather than the item (the reported Lillia case:
    // "2 items" quietly included Spellslinger's Shoes). Tier-2 boots land
    // after the first item, the convention players actually follow; the
    // tier-3 enchant lands where the model timed it and costs the DELTA
    // (its listed cost is cumulative and it replaces the tier-2 in the set).
    const metric = metricOf(name);
    const t2 = boots || "";
    const t3 = bootsUpgrade || "";
    const itemCost = (slug: string) => DATA.items?.[slug]?.cost ?? 3000;
    const upgradeAt = t3
      ? (bootsUpgradeAfter && bootsUpgradeAfter > 0
          ? Math.min(bootsUpgradeAfter, items.length) : 2)
      : 0;
    const t3Delta = t3 ? Math.max(300, itemCost(t3) - (t2 ? itemCost(t2) : 0)) : 0;

    type Purchase = { kind: "item" | "t2" | "t3"; slug: string; costG: number; itemCount: number };
    const purchasesFor = (order: string[], at: number): Purchase[] => {
      const seq: Purchase[] = [];
      order.forEach((slug, i) => {
        seq.push({ kind: "item", slug, costG: itemCost(slug), itemCount: i + 1 });
        if (i === 0 && t2) seq.push({ kind: "t2", slug: t2, costG: itemCost(t2), itemCount: i + 1 });
        if (i + 1 === at && t3) seq.push({ kind: "t3", slug: t3, costG: t3Delta, itemCount: i + 1 });
      });
      return seq;
    };

    // A Wild Rift game runs about 20 minutes on average, and income runs
    // ~650 gold per minute, so ~13,000 gold is everything a typical game
    // actually gets to buy. Stages past that line are dimmed and cannot win
    // the spike badge: Lillia's full build costs 17,600g, and calling that
    // "your spike" points players at a game that will never be played.
    const REACHABLE_GOLD = 13000;
    const target = dummyTarget(3000, 60, 45);
    const purchases = purchasesFor(items, upgradeAt);
    const owned: string[] = [];
    let gold = 0;
    const rows = purchases.map((purchase, i) => {
      if (purchase.kind === "t3" && t2) {
        const at = owned.indexOf(t2);
        if (at >= 0) owned.splice(at, 1);
      }
      owned.push(purchase.slug);
      gold += purchase.costG;
      const slugs = [...owned];
      const st = resolveStats(name, level, slugs, runeNames);
      const fight = duel(name, slugs, runeNames, target, level, 20, false);
      // Burst is the 3s rotation, the same window the Python engine's burst3
      // uses, so a mage's spike is measured on the fight she actually has.
      const burst = metric === "burst" && st
        ? Math.round(rotation(name, st, target, BURST_WINDOW, level)) : 0;
      const label = purchase.kind === "item"
        ? (i === purchases.length - 1 ? "Full"
           : `${purchase.itemCount} item${purchase.itemCount > 1 ? "s" : ""}`)
        : purchase.kind === "t2" ? "Boots" : "T3 boots";
      const hp = st ? Math.round(st.hp) : 0;
      const dps = fight?.dps ?? 0;
      return {
        idx: i + 1,
        kind: purchase.kind,
        label,
        slugs,
        gold,
        unreachable: gold > REACHABLE_GOLD,
        hp,
        dps,
        burst,
        // The number this champion is actually judged on.
        value: metric === "durability" ? hp : metric === "burst" ? burst : dps,
        ttk: fight?.ttk ?? null,
      };
    });
    if (rows.some((r) => !r.dps || !r.value)) return null;

    // Strongest spike = biggest marginal gain from the previous stage, but
    // only among stages a real game REACHES (see REACHABLE_GOLD above).
    //
    // WHAT counts as the gain follows the champion's job: a mage or assassin
    // spikes on BURST, a bruiser or marksman on SUSTAINED damage, a tank on
    // DURABILITY -- Malphite's spike is the fight he survives, not the one he
    // out-damages, and Lux's is the combo that kills, not second eight.
    let spike = 1;
    let best = 0;
    for (let i = 1; i < rows.length; i += 1) {
      if (rows[i].unreachable) break;
      const gain = rows[i].value - rows[i - 1].value;
      if (gain > best) { best = gain; spike = i + 1; }
    }
    return { rows, spike, spikeLabel: rows[spike - 1]?.label ?? "",
             purchasesFor, upgradeAt, t3, metric,
             spikeMetric: metric === "durability" ? ("durability" as const)
                        : metric === "burst" ? ("burst" as const) : ("damage" as const) };
  }, [name, items, boots, bootsUpgrade, bootsUpgradeAfter, runeNames, level]);

  // ENGINE ORDER CHECK: would any other purchase order of the SAME five
  // items reach power earlier? Wild Rift games are short, so the curve's
  // early half is what the order is for. DPS depends only on the SET of
  // items owned, so the 120 orderings collapse onto a few dozen distinct
  // simulations: for each ordering, walk the gold checkpoints, look up the
  // owned set's dps (cached), and score early checkpoints hardest. The
  // Gwen case that motivated this: Deathcap LAST is right (its cost starves
  // the early game; the check proves it), but the ladder's opening order
  // still left 5-12% early damage on the table.
  const orderCheck = useMemo(() => {
    if (!stages || items.length !== 5) return null;
    const cost = (slug: string) => DATA.items?.[slug]?.cost ?? 3000;
    // Checkpoints and weights follow the REQUESTED power curve, per the
    // owner's definition: Early optimizes immediate strength and cheap fast
    // spikes, Mid optimizes around 1-3 completed items, Late deliberately
    // trades the early game for scaling -- so a late-goal build must not be
    // reordered (or scored) as if it wanted an early spike. Gold-to-minute
    // at ~650/min: 3k=min 4.5, 5k=min 7.5, 7.5k=min 11.5, 10k=min 15.5,
    // 13k=min 20.
    const [CHECKPOINTS, WEIGHTS] =
      powerCurve === "early" ? [[3000, 5000, 7500], [3, 2, 1]]
      : powerCurve === "mid" ? [[4500, 7000, 9500], [1, 3, 2]]
      : powerCurve === "late" ? [[6000, 9500, 13000], [1, 2, 3]]
      : [[3000, 6000, 9000], [2, 2, 1]];
    const target = dummyTarget(3000, 60, 45);

    // The order check scores the SAME axis the spike badge uses, so the two
    // can never disagree about what "stronger earlier" means: burst for a
    // mage, sustained damage for a marksman, durability for a tank.
    const axis = stages.metric;
    const valueCache = new Map<string, number>();
    const dpsOf = (owned: string[]): number => {
      if (!owned.length) return 0;
      const key = [...owned].sort().join(",");
      let v = valueCache.get(key);
      if (v === undefined) {
        if (axis === "durability") {
          v = Number(resolveStats(name, level, owned, runeNames)?.hp ?? 0);
        } else if (axis === "burst") {
          const st = resolveStats(name, level, owned, runeNames);
          v = st ? rotation(name, st, target, BURST_WINDOW, level) : 0;
        } else {
          v = duel(name, owned, runeNames, target, level, 20, false)?.dps ?? 0;
        }
        valueCache.set(key, v);
      }
      return v;
    };

    // Boots are real purchases in the walk: tier-2 after the first item,
    // the tier-3 enchant (delta-priced) wherever `at` says -- the same
    // sequence the stage rows show, so the two never disagree.
    const score = (order: string[], at = stages.upgradeAt): number => {
      const seq = stages.purchasesFor(order, at);
      let total = 0;
      const weights = WEIGHTS;
      CHECKPOINTS.forEach((gold, i) => {
        const owned: string[] = [];
        let spent = 0;
        for (const purchase of seq) {
          spent += purchase.costG;
          if (spent > gold) break;
          if (purchase.kind === "t3" && boots) {
            const idx = owned.indexOf(boots);
            if (idx >= 0) owned.splice(idx, 1);
          }
          owned.push(purchase.slug);
        }
        total += dpsOf(owned) * weights[i];
      });
      return total;
    };

    // BOOTS TIMING CHECK: with boots as measured purchases, the engine can
    // ask when the tier-3 enchant actually pays: score the SHOWN item order
    // with the upgrade after 0 (never) through 5 items and compare against
    // the model's timing. This is the engine's answer to "when do T3 boots
    // give the best spike", including "not at all".
    let bootsTiming: { best: number; gainPct: number } | null = null;
    if (stages.t3) {
      const shownTiming = score(items, stages.upgradeAt);
      let bestAt = stages.upgradeAt;
      let bestScore = shownTiming;
      for (let at = 0; at <= items.length; at += 1) {
        if (at === stages.upgradeAt) continue;
        const sc = score(items, at);
        if (sc > bestScore) { bestScore = sc; bestAt = at; }
      }
      const timingGain = (bestScore - shownTiming) / shownTiming;
      if (bestAt !== stages.upgradeAt && timingGain >= 0.04) {
        bootsTiming = { best: bestAt, gainPct: Math.round(timingGain * 100) };
      }
    }

    const bestOf = (set: string[]): { score: number; order: string[] } => {
      const perms: string[][] = [];
      const permute = (rest: string[], acc: string[]) => {
        if (!rest.length) { perms.push(acc); return; }
        for (let i = 0; i < rest.length; i += 1) {
          permute([...rest.slice(0, i), ...rest.slice(i + 1)], [...acc, rest[i]]);
        }
      };
      permute(set, []);
      let bestScore = -1;
      let bestOrder = set;
      for (const perm of perms) {
        const sc = score(perm);
        if (sc > bestScore) { bestScore = sc; bestOrder = perm; }
      }
      return { score: bestScore, order: bestOrder };
    };

    const shown = score(items);
    if (shown <= 0) return null;
    const own = bestOf(items);
    const gain = (own.score - shown) / shown;

    // EARLY-GOAL SUBSTITUTION CHECK: with an early power curve requested, the
    // build's most expensive pieces are the suspects -- a cheaper item in
    // that slot may reach the spike sooner for the same gold. Candidates are
    // the model's own scored alternatives, filtered to legal, cheaper,
    // non-boots items. Compared best-order vs best-order, so a substitution
    // only wins on the ITEM, never on ordering luck.
    let swap: { out: string; in: string; gainPct: number } | null = null;
    if (powerCurve === "early" && candidates?.length) {
      const targets = items.filter((slug) => cost(slug) >= 3200);
      const pool = candidates
        .map((c) => c.item)
        .filter((slug) => slug && !items.includes(slug)
          && DATA.items?.[slug] && DATA.items[slug].category !== "Boots");
      for (const target of targets) {
        const rest = items.filter((s) => s !== target);
        for (const cand of pool) {
          if (cost(cand) > cost(target) - 200) continue;
          if (blockedItems([...rest])[cand]) continue;
          const sub = bestOf([...rest, cand]);
          const subGain = (sub.score - own.score) / own.score;
          if (subGain >= 0.05 && (!swap || subGain * own.score > 0)) {
            if (!swap || sub.score > own.score * (1 + swap.gainPct / 100)) {
              swap = { out: target, in: cand, gainPct: Math.round(subGain * 100) };
            }
          }
        }
      }
    }

    // Below 4% the reorder is noise against everything the sim cannot see
    // (lane safety, mana, component sizes); the shown order stands.
    if (gain < 0.04) return { verdict: "optimal" as const, swap, bootsTiming };
    return { verdict: "reorder" as const, order: own.order, gainPct: Math.round(gain * 100), swap, bootsTiming };
  }, [stages, items, boots, runeNames, name, level, powerCurve, candidates]);

  if (!stages) return null;
  const maxDps = Math.max(...stages.rows.map((r) => r.value), 1);

  const body = (
      <div className="space-y-2">
        {stages.rows.map((row) => (
          <div key={row.idx}
               className={`flex flex-wrap items-center gap-3 rounded-xl px-3 py-2 ${
                 row.idx === stages.spike ? "border border-gold/30 bg-gold/[0.06]" : "bg-white/[0.03]"} ${
                 row.unreachable ? "opacity-55" : ""}`}>
            <span className="w-16 shrink-0 text-xs font-bold uppercase tracking-wide text-faint">
              {row.label}
            </span>
            <span className="flex shrink-0 items-center gap-1">
              {row.slugs.map((slug, i) => (
                <img key={`${slug}-${i}`} src={itemIcon(slug)} alt={itemName(slug)} title={itemName(slug)}
                     width={26} height={26} className="rounded-md ring-1 ring-white/10" />
              ))}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                <span className="block h-full rounded-full bg-gradient-to-r from-accent/50 to-accent"
                      style={{ width: `${Math.round((row.value / maxDps) * 100)}%` }} />
              </span>
            </span>
            <span className="shrink-0 text-right text-xs tabular-nums">
              <span className="font-bold text-accent">
                {(stages.metric === "burst" ? row.burst : row.dps).toLocaleString()}
              </span>
              <span className="text-faint">{stages.metric === "burst" ? " burst" : " dps"}</span>
              <span className="ml-2 font-semibold text-text">{row.hp.toLocaleString()}</span>
              <span className="text-faint"> hp</span>
              {row.idx === stages.spike && (
                <span className="ml-2 rounded bg-gold/20 px-1.5 py-0.5 text-[0.6rem] font-bold uppercase text-gold">spike</span>
              )}
            </span>
          </div>
        ))}
      </div>
  );

  const heading = (
    <>
      <span className="block text-sm font-bold text-text">When this build spikes</span>
      <span className="text-xs font-normal text-faint">
        Engine-measured at each purchase, not a guess. Strongest{" "}
        {stages.spikeMetric} spike:{" "}
        <span className="font-semibold text-gold">{stages.spikeLabel.toLowerCase()}</span>
      </span>
    </>
  );
  const footnote = (
    <>
      {orderCheck?.verdict === "optimal" && (
        <p className="mt-2.5 rounded-lg bg-emerald-400/[0.07] px-2.5 py-1.5 text-[0.7rem] leading-relaxed text-emerald-300/90">
          Order check: the engine simulated all 120 purchase orders of these five items
          at early-gold checkpoints; the shown order is already among the strongest
          early curves.
        </p>
      )}
      {orderCheck?.verdict === "reorder" && (
        <p className="mt-2.5 rounded-lg bg-gold/[0.07] px-2.5 py-1.5 text-[0.7rem] leading-relaxed text-gold/90">
          Order check: the same items reach ~{orderCheck.gainPct}% more early{" "}
          {stages.spikeMetric} bought as{" "}
          <span className="font-semibold">
            {orderCheck.order.map((slug) => itemName(slug)).join(" → ")}
          </span>
          . Pure value-per-gold against a reference target; the shown order may still
          win on lane safety, mana or component costs.
        </p>
      )}
      {orderCheck?.bootsTiming && (
        <p className="mt-2.5 rounded-lg bg-gold/[0.07] px-2.5 py-1.5 text-[0.7rem] leading-relaxed text-gold/90">
          Boots check: {orderCheck.bootsTiming.best === 0
            ? "keeping tier-2 boots all game"
            : `upgrading to ${itemName(stages.t3)} after ${orderCheck.bootsTiming.best} item${
                orderCheck.bootsTiming.best > 1 ? "s" : ""}`} reaches
          ~{orderCheck.bootsTiming.gainPct}% more early {stages.spikeMetric} than the
          shown timing. The ~1,000g enchant competes with your next item; this is when the
          engine says it pays.
        </p>
      )}
      {orderCheck?.swap && (
        <p className="mt-2.5 rounded-lg bg-accent/[0.07] px-2.5 py-1.5 text-[0.7rem] leading-relaxed text-accent/90">
          Early-spike check: for the Early game goal, swapping{" "}
          <span className="font-semibold">{itemName(orderCheck.swap.out)}</span> for{" "}
          <span className="font-semibold">{itemName(orderCheck.swap.in)}</span> reaches
          ~{orderCheck.swap.gainPct}% more {stages.spikeMetric} inside the
          early window at the same gold. {itemName(orderCheck.swap.out)} still wins long games; this is the
          trade the Early goal asks about.
        </p>
      )}
      <p className="mt-2.5 text-[0.7rem] leading-relaxed text-faint">
        Measured against a reference target (3,000 HP, 60 armor, 45 MR) with this
        build&rsquo;s runes, on the axis this champion is judged on: burst over three
        seconds for mages and assassins, sustained damage per second for bruisers and
        marksmen, effective health for tanks. Tier-2 boots and the tier-3 enchant are their own measured
        purchases, so a stage&rsquo;s jump is one buy&rsquo;s worth of power. Dimmed stages
        cost more gold than an average 20-minute game provides, and the spike is only
        awarded among the stages a real game reaches. The same maths as the Custom
        Lab&rsquo;s fight, so the numbers agree across the site.
      </p>
    </>
  );

  if (bare) {
    return (
      <div>
        <div className="mb-2">{heading}</div>
        {body}
        {footnote}
      </div>
    );
  }
  return (
    <details open className="glass group rounded-2xl p-4">
      <summary className="mb-3 flex cursor-pointer list-none items-center justify-between gap-2">
        <span className="min-w-0">{heading}</span>
        <span aria-hidden className="shrink-0 text-accent transition group-open:rotate-180">⌄</span>
      </summary>
      {body}
      {footnote}
    </details>
  );
}
