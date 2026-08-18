"use client";

import { useMemo } from "react";
import { duel, dummyTarget, resolveStats } from "@/lib/engine";
import { hasSimulatableKit } from "@/lib/customizer-data";
import engineData from "@/data/engine.json";

/* eslint-disable @next/next/no-img-element */

const DATA = engineData as {
  items?: Record<string, { name?: string; icon?: string; cost?: number }>;
  formulas?: Record<string, { mechanics?: { kind?: string }[] }>;
};

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
export function BuildStages({ name, items, boots, bootsUpgrade, bootsUpgradeAfter, runeNames, level = 15, bare = false }: {
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
}) {
  const stages = useMemo(() => {
    if (!items.length || !hasSimulatableKit(name)) return null;
    // Only the base form is modelled for transformers; skip rather than lie.
    if ((DATA.formulas?.[name]?.mechanics ?? []).some((m) => m.kind === "transform")) return null;

    const finishedBoots = bootsUpgrade || boots || "";
    // Boots join where the strip shows them landing: the model-chosen upgrade
    // timing, or the old fixed 2 for builds that predate the field. A skipped
    // upgrade (bootsUpgradeAfter 0) means finishedBoots is already the tier-2,
    // which still joins after two items -- the timing decision is about the
    // enchant, not about owning boots.
    const bootsAt = bootsUpgradeAfter && bootsUpgradeAfter > 0
      ? Math.min(bootsUpgradeAfter, Math.max(items.length, 1))
      : 2;
    const order: string[][] = [];
    for (let k = 1; k <= items.length; k += 1) {
      const prefix = items.slice(0, k);
      if (k >= bootsAt && finishedBoots) prefix.splice(bootsAt, 0, finishedBoots);
      order.push(prefix);
    }

    const target = dummyTarget(3000, 60, 45);
    const itemCost = (slug: string) => DATA.items?.[slug]?.cost ?? 3000;
    const rows = order.map((slugs, i) => {
      const st = resolveStats(name, level, slugs, runeNames);
      const fight = duel(name, slugs, runeNames, target, level, 20, false);
      const gold = slugs.reduce((sum, slug) => sum + itemCost(slug), 0);
      return {
        count: i + 1,
        slugs,
        gold,
        // ~650 gold/min is a farming laner or jungler including passive
        // income; precise enough for a minute MARK, not a promise.
        minute: Math.round(gold / 650),
        hp: st ? Math.round(st.hp) : 0,
        dps: fight?.dps ?? 0,
        ttk: fight?.ttk ?? null,
      };
    });
    if (rows.some((r) => !r.dps)) return null;

    // Strongest spike = biggest marginal DPS gain from the previous stage,
    // but only among stages a real game REACHES. Lillia's full build costs
    // 17,600g -- minute 27 at real income -- and calling that "your spike"
    // points players at a game that will never be played. ~10.5k gold is
    // roughly minute 16, the long end of a real Wild Rift game.
    const REACHABLE_GOLD = 10500;
    let spike = 1;
    let best = 0;
    for (let i = 1; i < rows.length; i += 1) {
      if (rows[i].gold > REACHABLE_GOLD) break;
      const gain = rows[i].dps - rows[i - 1].dps;
      if (gain > best) { best = gain; spike = i + 1; }
    }
    return { rows, spike };
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
    const finishedBoots = bootsUpgrade || boots || "";
    const bootsAt = bootsUpgradeAfter && bootsUpgradeAfter > 0
      ? Math.min(bootsUpgradeAfter, items.length) : 2;
    const cost = (slug: string) => DATA.items?.[slug]?.cost ?? 3000;
    // ~min 4.5 / 7.5 / 11.5 at real income. The first cut used 9.6k as the
    // third checkpoint, which is minute ~15 -- too late to call "early".
    const CHECKPOINTS = [3000, 5000, 7500];
    const target = dummyTarget(3000, 60, 45);

    const dpsCache = new Map<string, number>();
    const dpsOf = (owned: string[]): number => {
      if (!owned.length) return 0;
      const key = [...owned].sort().join(",");
      let v = dpsCache.get(key);
      if (v === undefined) {
        v = duel(name, owned, runeNames, target, level, 20, false)?.dps ?? 0;
        dpsCache.set(key, v);
      }
      return v;
    };

    const score = (order: string[]): number => {
      // Purchase sequence mirrors the strip: boots complete after `bootsAt`.
      const seq = [...order];
      if (finishedBoots) seq.splice(bootsAt, 0, finishedBoots);
      let total = 0;
      const weights = [3, 2, 1];
      CHECKPOINTS.forEach((gold, i) => {
        const owned: string[] = [];
        let spent = 0;
        for (const slug of seq) {
          spent += cost(slug);
          if (spent > gold) break;
          owned.push(slug);
        }
        total += dpsOf(owned) * weights[i];
      });
      return total;
    };

    const perms: string[][] = [];
    const permute = (rest: string[], acc: string[]) => {
      if (!rest.length) { perms.push(acc); return; }
      for (let i = 0; i < rest.length; i += 1) {
        permute([...rest.slice(0, i), ...rest.slice(i + 1)], [...acc, rest[i]]);
      }
    };
    permute(items, []);

    const shown = score(items);
    let best = shown;
    let bestOrder = items;
    for (const perm of perms) {
      const sc = score(perm);
      if (sc > best) { best = sc; bestOrder = perm; }
    }
    if (shown <= 0) return null;
    const gain = (best - shown) / shown;
    // Below 4% the reorder is noise against everything the sim cannot see
    // (lane safety, mana, component sizes); the shown order stands.
    if (gain < 0.04) return { verdict: "optimal" as const };
    return { verdict: "reorder" as const, order: bestOrder, gainPct: Math.round(gain * 100) };
  }, [stages, items, boots, bootsUpgrade, bootsUpgradeAfter, runeNames, name, level]);

  if (!stages) return null;
  const maxDps = Math.max(...stages.rows.map((r) => r.dps), 1);

  const body = (
      <div className="space-y-2">
        {stages.rows.map((row) => (
          <div key={row.count}
               className={`flex flex-wrap items-center gap-3 rounded-xl px-3 py-2 ${
                 row.count === stages.spike ? "border border-gold/30 bg-gold/[0.06]" : "bg-white/[0.03]"} ${
                 row.minute > 16 ? "opacity-55" : ""}`}>
            <span className="w-16 shrink-0 text-xs font-bold uppercase tracking-wide text-faint">
              {row.count === stages.rows.length ? "Full" : `${row.count} item${row.count > 1 ? "s" : ""}`}
              <span className={`block text-[0.6rem] font-semibold normal-case ${
                row.minute > 16 ? "text-bad/70" : "text-faint/80"}`}>
                ~min {row.minute}
              </span>
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
                      style={{ width: `${Math.round((row.dps / maxDps) * 100)}%` }} />
              </span>
            </span>
            <span className="shrink-0 text-right text-xs tabular-nums">
              <span className="font-bold text-accent">{row.dps.toLocaleString()}</span>
              <span className="text-faint"> dps</span>
              <span className="ml-2 font-semibold text-text">{row.hp.toLocaleString()}</span>
              <span className="text-faint"> hp</span>
              {row.count === stages.spike && (
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
        Engine-measured at each purchase, not a guess. Strongest spike:{" "}
        <span className="font-semibold text-gold">{stages.spike} item{stages.spike > 1 ? "s" : ""}</span>
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
          Order check: the same items reach ~{orderCheck.gainPct}% more early damage
          bought as{" "}
          <span className="font-semibold">
            {orderCheck.order.map((slug) => itemName(slug)).join(" → ")}
          </span>
          . Pure damage-per-gold against a reference target; the shown order may still
          win on lane safety, mana or component costs.
        </p>
      )}
      <p className="mt-2.5 text-[0.7rem] leading-relaxed text-faint">
        Damage per second against a reference target (3,000 HP, 60 armor, 45 MR) with this
        build&rsquo;s runes, boots joining where the strip shows them landing. Minute marks
        assume ~650 gold per minute of real income; dimmed stages are ones most games never
        reach, and the spike is only awarded among stages a real game gets to. The same
        maths as the Custom Lab&rsquo;s fight, so the numbers agree across the site.
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
