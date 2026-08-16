"use client";

import { useMemo } from "react";
import { duel, dummyTarget, resolveStats } from "@/lib/engine";
import { hasSimulatableKit } from "@/lib/customizer-data";
import engineData from "@/data/engine.json";

/* eslint-disable @next/next/no-img-element */

const DATA = engineData as {
  items?: Record<string, { name?: string; icon?: string }>;
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
    const rows = order.map((slugs, i) => {
      const st = resolveStats(name, level, slugs, runeNames);
      const fight = duel(name, slugs, runeNames, target, level, 20, false);
      return {
        count: i + 1,
        slugs,
        hp: st ? Math.round(st.hp) : 0,
        dps: fight?.dps ?? 0,
        ttk: fight?.ttk ?? null,
      };
    });
    if (rows.some((r) => !r.dps)) return null;

    // Strongest spike = biggest marginal DPS gain from the previous stage.
    let spike = 1;
    let best = 0;
    for (let i = 1; i < rows.length; i += 1) {
      const gain = rows[i].dps - rows[i - 1].dps;
      if (gain > best) { best = gain; spike = i + 1; }
    }
    return { rows, spike };
  }, [name, items, boots, bootsUpgrade, bootsUpgradeAfter, runeNames, level]);

  if (!stages) return null;
  const maxDps = Math.max(...stages.rows.map((r) => r.dps), 1);

  const body = (
      <div className="space-y-2">
        {stages.rows.map((row) => (
          <div key={row.count}
               className={`flex flex-wrap items-center gap-3 rounded-xl px-3 py-2 ${
                 row.count === stages.spike ? "border border-gold/30 bg-gold/[0.06]" : "bg-white/[0.03]"}`}>
            <span className="w-14 shrink-0 text-xs font-bold uppercase tracking-wide text-faint">
              {row.count === stages.rows.length ? "Full" : `${row.count} item${row.count > 1 ? "s" : ""}`}
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
    <p className="mt-2.5 text-[0.7rem] leading-relaxed text-faint">
      Damage per second against a reference target (3,000 HP, 60 armor, 45 MR) with this
      build&rsquo;s runes, boots joining where the strip shows them landing. The same maths
      as the Custom Lab&rsquo;s fight, so the numbers agree across the site.
    </p>
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
