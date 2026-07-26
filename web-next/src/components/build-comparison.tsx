"use client";

import { useMemo, useState } from "react";
import { customizerItems, listedBuildStats } from "@/lib/customizer-data";
import { scaledBuildStats, scalingSources } from "@/lib/build-scaling";
import { ShareBuildButton } from "@/components/share-build";
import { getChampions } from "@/lib/data";

/* eslint-disable @next/next/no-img-element */

export interface ComparableBuild {
  id: string;
  label: string;
  itemSlugs: string[];
  runeNames?: string[];
}

type ComparisonVerdict = {
  winner: "left" | "right" | "tie";
  leftScore: number;
  rightScore: number;
  confidence: number;
  reason: string;
  decidingFactors: string[];
  tradeoff: string;
  error?: string;
};

const GOALS = [
  ["overall", "Overall win rate"],
  ["burst", "Burst / one-shot"],
  ["sustained", "Sustained damage"],
  ["survivability", "Survivability"],
  ["early", "Early power"],
] as const;

const ROWS = [
  ["ad", "Attack Damage", ""],
  ["ap", "Ability Power", ""],
  ["hp", "Health", ""],
  ["armor", "Armor", ""],
  ["mr", "Magic Resist", ""],
  ["attackSpeed", "Attack Speed", ""],
  ["crit", "Critical Rate", "%"],
  ["haste", "General AH", ""],
  ["basicAbilityHaste", "Basic Ability AH", ""],
  ["ultimateAbilityHaste", "Ultimate AH", ""],
  ["moveSpeed", "Move Speed", ""],
  ["mana", "Mana", ""],
  ["physicalPenFlat", "Flat Armor Pen", ""],
  ["physicalPen", "Armor Pen", "%"],
  ["magicPenFlat", "Flat Magic Pen", ""],
  ["magicPen", "Magic Pen", "%"],
  ["omnivamp", "Omnivamp", "%"],
  ["physicalVamp", "Physical Vamp", "%"],
  ["tenacity", "Tenacity", "%"],
  ["healShieldPower", "Heal & Shield Power", "%"],
  ["itemCost", "Total Item Cost", "g"],
] as const;

export function BuildComparison({
  champion,
  current,
  choices,
  level = 15,
}: {
  champion: string;
  current: ComparableBuild;
  choices: ComparableBuild[];
  level?: number;
}) {
  const available = choices.filter((choice) => choice.id !== current.id);
  const [targetId, setTargetId] = useState(available[0]?.id ?? "");
  const [goal, setGoal] = useState("overall");
  const [evaluating, setEvaluating] = useState(false);
  const [verdict, setVerdict] = useState<{ key: string; data: ComparisonVerdict } | null>(null);
  const target = available.find((choice) => choice.id === targetId) ?? available[0];
  const items = useMemo(() => new Map(customizerItems().map((item) => [item.slug, item])), []);
  // Shared comparison links land on the champion's build page; that is as close
  // as a URL can get to "these two builds side by side".
  const championSlug = useMemo(
    () => getChampions().find((entry) => entry.name === champion)?.slug ?? "",
    [champion],
  );
  // A stacking build and a static build are not comparable on guaranteed stats
  // alone, which is exactly the comparison people come here to make.
  const [scaled, setScaled] = useState(false);
  const readStats = (build: ComparableBuild | undefined) => {
    if (!build) return null;
    return scaled
      ? scaledBuildStats(champion, build.itemSlugs, level, build.runeNames)?.stats ?? null
      : listedBuildStats(champion, build.itemSlugs, level, build.runeNames);
  };
  const left = readStats(current);
  const right = readStats(target);
  const canScale = [
    ...scalingSources(current.itemSlugs, current.runeNames ?? []),
    ...scalingSources(target?.itemSlugs ?? [], target?.runeNames ?? []),
  ].length > 0;

  if (!target || !left || !right) return null;
  const activeRows = ROWS.filter(([key]) => left[key] !== 0 || right[key] !== 0);
  const verdictKey = JSON.stringify([champion, goal, current.itemSlugs, current.runeNames, target.itemSlugs, target.runeNames]);
  const activeVerdict = verdict?.key === verdictKey ? verdict.data : null;
  const canEvaluate = current.itemSlugs.length > 0 && target.itemSlugs.length > 0;

  const evaluate = async () => {
    if (!canEvaluate || evaluating) return;
    setEvaluating(true);
    try {
      const response = await fetch("/api/compare-builds", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ champion, goal, left: current, right: target }),
      });
      const data = await response.json() as ComparisonVerdict;
      setVerdict({ key: verdictKey, data });
    } catch (error) {
      setVerdict({ key: verdictKey, data: { winner: "tie", leftScore: 0, rightScore: 0, confidence: 0, reason: "", decidingFactors: [], tradeoff: "", error: String(error) } });
    } finally {
      setEvaluating(false);
    }
  };

  return (
    <details className="glass group rounded-2xl">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-4">
        <span>
          <span className="block text-sm font-bold text-text">Compare builds</span>
          <span className="text-xs font-normal text-faint">Items, cost, runes, and transparent listed stats</span>
        </span>
        <span aria-hidden className="text-accent transition group-open:rotate-180">⌄</span>
      </summary>
      <div className="border-t border-line/60 p-4">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-xs font-bold uppercase tracking-wide text-faint">Compare with</span>
          <select
            value={target.id}
            onChange={(event) => setTargetId(event.target.value)}
            aria-label="Build to compare against"
            className="rounded-lg border border-line bg-[#0e1322] px-2.5 py-1.5 text-sm text-text outline-none focus:border-accent/60"
          >
            {available.map((choice) => <option key={choice.id} value={choice.id}>{choice.label}</option>)}
          </select>
          <select
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            aria-label="Comparison goal"
            title="The winner is judged for this goal"
            className="rounded-lg border border-line bg-[#0e1322] px-2.5 py-1.5 text-sm text-text outline-none focus:border-accent/60"
          >
            {GOALS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <button
            type="button"
            onClick={evaluate}
            disabled={!canEvaluate || evaluating}
            title={canEvaluate ? "Judge both complete builds for the selected goal" : "Add at least one item before comparing"}
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-bold text-black transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {evaluating ? "Evaluating…" : "Judge builds"}
          </button>
          {canScale && (
            <div className="flex items-center gap-0.5 rounded-lg border border-line bg-white/[0.03] p-0.5">
              <button
                onClick={() => setScaled(false)}
                aria-pressed={!scaled}
                title="Compare on stats both builds are guaranteed to have"
                className={`rounded-md px-2.5 py-1 text-[0.65rem] font-bold transition ${!scaled ? "bg-accent/20 text-accent" : "text-muted hover:text-text"}`}
              >
                Guaranteed
              </button>
              <button
                onClick={() => setScaled(true)}
                aria-pressed={scaled}
                title="Compare with stacks, ramps and stat conversions at maximum"
                className={`rounded-md px-2.5 py-1 text-[0.65rem] font-bold transition ${scaled ? "bg-accent/20 text-accent" : "text-muted hover:text-text"}`}
              >
                Fully scaled
              </button>
            </div>
          )}
          <ShareBuildButton
            className="ml-auto"
            path={`/build?champion=${encodeURIComponent(championSlug)}`}
            title={`${champion}: ${current.label} vs ${target.label}`}
            text={`${champion} build comparison on WrTrueMeta: ${current.label} against ${target.label}.`}
            label="Share comparison"
          />
        </div>

        {activeVerdict && (
          activeVerdict.error ? (
            <p className="mb-4 rounded-xl border border-bad/30 bg-bad/10 p-3 text-sm text-bad">Could not compare: {activeVerdict.error}</p>
          ) : (
            <VerdictPanel verdict={activeVerdict} leftLabel={current.label} rightLabel={target.label} />
          )
        )}

        <div className="grid gap-3 md:grid-cols-2">
          <BuildSummary build={current} items={items} />
          <BuildSummary build={target} items={items} />
        </div>

        <div className="mt-4 overflow-hidden rounded-xl border border-line/60">
          <div className="grid grid-cols-[minmax(7rem,1fr)_minmax(5rem,0.7fr)_minmax(5rem,0.7fr)] bg-white/[0.04] px-3 py-2 text-[0.62rem] font-bold uppercase tracking-wide text-faint">
            <span>Stat</span>
            <span className="text-right">{current.label}</span>
            <span className="text-right">{target.label}</span>
          </div>
          {activeRows.map(([key, label, suffix]) => (
            <ComparisonRow key={key} label={label} suffix={suffix} left={left[key]} right={right[key]} />
          ))}
        </div>
        <p className="mt-3 text-xs text-faint">
          {scaled
            ? "Fully scaled: stacking items, ramping passives and stat conversions are counted at their maximum modelled value. Targets and triggered damage procs remain descriptive rather than simulated."
            : "This compares champion base stats plus unconditional listed item stats. Rune procs, stacks, targets, and triggered passives remain descriptive rather than simulated."}
        </p>
      </div>
    </details>
  );
}

function VerdictPanel({ verdict, leftLabel, rightLabel }: { verdict: ComparisonVerdict; leftLabel: string; rightLabel: string }) {
  const winnerLabel = verdict.winner === "left" ? leftLabel : verdict.winner === "right" ? rightLabel : "Tie";
  return (
    <div className="mb-4 rounded-xl border border-accent/30 bg-accent/[0.07] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-bold text-text">
          Winner: <span className="text-accent">{winnerLabel}</span>
        </p>
        <p className="text-xs font-semibold text-muted">
          {leftLabel} {verdict.leftScore} · {rightLabel} {verdict.rightScore} · {verdict.confidence}% confidence
        </p>
      </div>
      <p className="mt-2 text-sm text-muted">{verdict.reason}</p>
      {verdict.decidingFactors.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs text-muted">
          {verdict.decidingFactors.map((factor, index) => <li key={index}>• {factor}</li>)}
        </ul>
      )}
      {verdict.tradeoff && <p className="mt-2 text-xs text-faint"><span className="font-semibold text-muted">Losing build’s edge:</span> {verdict.tradeoff}</p>}
    </div>
  );
}

function BuildSummary({ build, items }: { build: ComparableBuild; items: Map<string, ReturnType<typeof customizerItems>[number]> }) {
  return (
    <div className="rounded-xl bg-white/[0.035] p-3">
      <p className="mb-2 text-sm font-bold text-text">{build.label}</p>
      <div className="flex min-h-9 flex-wrap gap-1.5">
        {build.itemSlugs.length ? build.itemSlugs.map((slug, index) => {
          const item = items.get(slug);
          return item ? (
            <img key={`${slug}-${index}`} src={item.icon} alt={item.name} title={`${item.name} · ${item.cost.toLocaleString()}g`} width={34} height={34} className="rounded-md ring-1 ring-white/10" />
          ) : null;
        }) : <span className="text-xs text-faint">No items selected yet.</span>}
      </div>
      {build.runeNames?.length ? (
        <p className="mt-2 line-clamp-2 text-xs text-muted">Runes: {build.runeNames.join(" · ")}</p>
      ) : null}
    </div>
  );
}

function ComparisonRow({ label, suffix, left, right }: { label: string; suffix: string; left: number; right: number }) {
  const format = (value: number) => `${(Math.round(value * 100) / 100).toLocaleString()}${suffix}`;
  return (
    <div className="grid grid-cols-[minmax(7rem,1fr)_minmax(5rem,0.7fr)_minmax(5rem,0.7fr)] border-t border-line/40 px-3 py-2 text-xs">
      <span className="text-muted">{label}</span>
      <span className={left !== right ? "text-right font-semibold text-text" : "text-right text-muted"}>{format(left)}</span>
      <span className={right !== left ? "text-right font-semibold text-text" : "text-right text-muted"}>{format(right)}</span>
    </div>
  );
}
