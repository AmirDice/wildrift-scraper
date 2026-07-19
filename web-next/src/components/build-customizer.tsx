"use client";

import { useMemo, useState } from "react";
import type { Build, ChampionBuilds } from "@/lib/builds";
import { abilityBreakdown, analyzeBuild, attackProfile, buildIssues, engineItems, engineRunes, liveMetrics } from "@/lib/engine";
import { SimReadout } from "@/components/build-view";
import { MonteCarloComparePanel } from "@/components/monte-carlo-compare";

/* eslint-disable @next/next/no-img-element */

type RunePick = { keystone: string; tree: string; minors: [string, string, string]; flex: string };

function fromBuild(b: Build): { items: string[]; boots: string; runes: RunePick } {
  return {
    items: b.coreBuild.map((i) => i.slug),
    boots: b.boots?.slug ?? "",
    runes: {
      keystone: b.runes.keystone?.name ?? "",
      tree: b.runes.primaryTree,
      minors: [
        b.runes.treeMinors[0]?.name ?? "",
        b.runes.treeMinors[1]?.name ?? "",
        b.runes.treeMinors[2]?.name ?? "",
      ],
      flex: b.runes.flexMinor?.name ?? "",
    },
  };
}

const EMPTY_STATE = { items: [] as string[], boots: "", runes: { keystone: "", tree: "", minors: ["", "", ""] as [string, string, string], flex: "" } };
// Wild Rift minor-rune paths. Keystone is chosen independently of these.
const TREES = ["Domination", "Precision", "Resolve", "Sorcery"] as const;

export function BuildCustomizer({ name, data }: { name: string; data: ChampionBuilds }) {
  const variants = data.variants?.length ? data.variants : Object.keys(data.builds);
  const [variant, setVariant] = useState(variants[0]);
  const base = data.builds[variant];
  // start EMPTY: the sandbox shows the champion's bare base stats, and every
  // item/rune the user adds shows its delta. "Start from" loads a variant.
  // The minor TREE is seeded from the current build, else the tree-minor slots
  // filter on tree === "" and show nothing (the reported bug). In Wild Rift the
  // keystone is independent of the minor path, so the tree is its own control.
  const [state, setState] = useState(() => ({
    ...EMPTY_STATE,
    runes: { ...EMPTY_STATE.runes, tree: base?.runes.primaryTree || "Precision" },
  }));
  const [level, setLevel] = useState(15);
  const [picker, setPicker] = useState<{ kind: "item" | "boots" | "keystone" | "minor" | "flex"; idx?: number } | null>(null);
  const [query, setQuery] = useState("");

  const allItems = useMemo(() => engineItems(), []);
  const allRunes = useMemo(() => engineRunes(), []);
  const itemMeta = useMemo(() => new Map(allItems.map((i) => [i.slug, i])), [allItems]);
  const runeMeta = useMemo(() => new Map(allRunes.map((r) => [r.name, r])), [allRunes]);

  const allSlugs = [...state.items.filter(Boolean), ...(state.boots ? [state.boots] : [])];
  const runeNames = [state.runes.keystone, ...state.runes.minors, state.runes.flex].filter(Boolean);
  const baseState = useMemo(() => fromBuild(base), [base]);
  const baseSlugs = [...baseState.items, ...(baseState.boots ? [baseState.boots] : [])];
  const baseRunes = [baseState.runes.keystone, ...baseState.runes.minors, baseState.runes.flex].filter(Boolean);
  const edited = allSlugs.length > 0 || runeNames.length > 0;
  // bare champion at this level vs the current sandbox build -> per-stat delta
  const bareM = useMemo(() => liveMetrics(name, [], [], variant, level), [name, variant, level]);
  const m = liveMetrics(name, allSlugs, runeNames, variant, level);
  const abilities = useMemo(() => abilityBreakdown(name, allSlugs, runeNames, level), [name, allSlugs.join(","), runeNames.join(","), level]);
  const style = attackProfile(name, allSlugs, runeNames);
  const analysis = useMemo(
    () => (allSlugs.length ? analyzeBuild(name, allSlugs, runeNames) : null),
    [name, allSlugs.join(","), runeNames.join(",")],
  );
  const baseScore = base.engine?.score;
  const issues = [
    ...buildIssues(allSlugs),
    ...(new Set(runeNames).size !== runeNames.length ? ["duplicate rune"] : []),
  ];

  const reset = (v: string) => {
    setVariant(v);
    setState(fromBuild(data.builds[v]));
    setPicker(null);
  };

  const pickItem = (slug: string) => {
    setState((s) => {
      if (picker?.kind === "boots") return { ...s, boots: slug };
      const items = [...s.items];
      const idx = picker?.idx ?? 0;
      if (slug === "") items.splice(idx, 1);     // unequip: drop the slot
      else if (idx >= items.length) items.push(slug); // add a new item
      else items[idx] = slug;
      return { ...s, items };
    });
    setPicker(null);
    setQuery("");
  };
  const pickRune = (rn: string) => {
    setState((s) => {
      const r = { ...s.runes };
      if (picker?.kind === "keystone") {
        // WR keystones are NOT tied to a tree (the scrape tags them all
        // "Keystone"), so picking one must not touch the minor path.
        r.keystone = rn;
      } else if (picker?.kind === "flex") r.flex = rn;
      else if (picker?.kind === "minor") {
        const minors = [...r.minors] as RunePick["minors"];
        minors[picker.idx ?? 0] = rn;
        r.minors = minors;
      }
      return { ...s, runes: r };
    });
    setPicker(null);
    setQuery("");
  };
  const removeCurrent = () => {
    if (!picker) return;
    if (picker.kind === "item" || picker.kind === "boots") pickItem("");
    else pickRune("");
  };

  const candidates = useMemo(() => {
    if (!picker) return [];
    const q = query.toLowerCase();
    if (picker.kind === "item" || picker.kind === "boots") {
      return allItems
        .filter((i) => (picker.kind === "boots" ? i.category === "Boots" : i.category !== "Boots"))
        .filter((i) => i.name.toLowerCase().includes(q))
        .sort((a, b) => a.name.localeCompare(b.name));
    }
    if (picker.kind === "keystone")
      return allRunes.filter((r) => r.type === "Keystone" && r.name.toLowerCase().includes(q));
    if (picker.kind === "flex")
      return allRunes.filter((r) => r.type === "Minor" && r.name.toLowerCase().includes(q));
    // tree minor: correct slot, constrained to the chosen tree (all trees if
    // none set, so the picker is never empty).
    const slot = (picker.idx ?? 0) + 1;
    return allRunes.filter(
      (r) => r.type === "Minor" && r.slot === slot
        && (!state.runes.tree || r.tree === state.runes.tree)
        && r.name.toLowerCase().includes(q));
  }, [picker, query, allItems, allRunes, state.runes.tree]);

  const Tile = ({ icon, label, onClick, size = 40, round = false }: {
    icon?: string; label: string; onClick: () => void; size?: number; round?: boolean;
  }) => (
    <button
      onClick={onClick}
      title={label}
      className="flex flex-col items-center gap-1 rounded-lg p-1 transition hover:bg-white/[0.06]"
    >
      {icon ? (
        <img src={icon} alt={label} width={size} height={size}
             className={`${round ? "rounded-full" : "rounded-lg"} ring-1 ring-white/15`}
             style={{ width: size, height: size }} />
      ) : (
        <span className={`grid place-items-center ${round ? "rounded-full" : "rounded-lg"} bg-white/[0.06] text-faint`}
              style={{ width: size, height: size }}>+</span>
      )}
    </button>
  );

  return (
    <div className="glass rounded-2xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">
          Customize <span className="normal-case text-faint/70">· build from scratch, watch every stat change</span>
        </p>
        <div className="flex items-center gap-1.5">
          <select
            value=""
            onChange={(e) => e.target.value && reset(e.target.value)}
            className="rounded-lg border border-line bg-[#0e1322] px-2 py-1 text-xs text-muted"
          >
            <option value="">start from…</option>
            {variants.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <button onClick={() => { setState(EMPTY_STATE); setPicker(null); }}
                  className="rounded-lg border border-line px-2 py-1 text-xs text-muted transition hover:text-text">
            clear
          </button>
        </div>
      </div>

      {/* level slider */}
      <div className="mt-3 flex items-center gap-3 rounded-xl bg-white/[0.03] px-3 py-2">
        <span className="shrink-0 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Level</span>
        <input type="range" min={1} max={15} value={level} onChange={(e) => setLevel(Number(e.target.value))}
               className="h-1.5 flex-1 cursor-pointer accent-[var(--color-accent)]" aria-label="Champion level" />
        <span className="w-6 shrink-0 text-right text-sm font-bold text-accent">{level}</span>
      </div>

      {/* item slots */}
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {state.items.map((slug, i) => (
          <Tile key={`${slug}-${i}`} icon={itemMeta.get(slug)?.icon}
                label={itemMeta.get(slug)?.name ?? "pick"}
                onClick={() => { setPicker({ kind: "item", idx: i }); setQuery(""); }} />
        ))}
        {state.items.length < 6 && (
          <Tile label="add item"
                onClick={() => { setPicker({ kind: "item", idx: state.items.length }); setQuery(""); }} />
        )}
        <span className="text-faint">+</span>
        <Tile icon={itemMeta.get(state.boots)?.icon} label={itemMeta.get(state.boots)?.name ?? "boots"}
              size={36} onClick={() => { setPicker({ kind: "boots" }); setQuery(""); }} />
        <span className="mx-1 h-8 w-px bg-line" />
        <Tile icon={runeMeta.get(state.runes.keystone)?.icon} label={state.runes.keystone || "keystone"}
              size={40} round onClick={() => { setPicker({ kind: "keystone" }); setQuery(""); }} />
        {/* minor path selector: switching resets the 3 minors */}
        <select
          value={state.runes.tree}
          onChange={(e) => setState((s) => ({ ...s, runes: { ...s.runes, tree: e.target.value, minors: ["", "", ""] } }))}
          className="rounded-lg border border-line bg-white/[0.04] px-1.5 py-1 text-xs outline-none"
          title="Minor rune path"
        >
          {TREES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        {state.runes.minors.map((rn, i) => (
          <Tile key={`${rn}-${i}`} icon={runeMeta.get(rn)?.icon} label={rn || `slot ${i + 1}`}
                size={32} round onClick={() => { setPicker({ kind: "minor", idx: i }); setQuery(""); }} />
        ))}
        <Tile icon={runeMeta.get(state.runes.flex)?.icon} label={state.runes.flex || "flex"}
              size={32} round onClick={() => { setPicker({ kind: "flex" }); setQuery(""); }} />
      </div>

      {/* picker */}
      {picker && (
        <div className="mt-3 rounded-xl border border-line bg-[#0d1220] p-3">
          <div className="flex items-center gap-2">
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={picker.kind === "minor" ? `${state.runes.tree} slot ${(picker.idx ?? 0) + 1}…` : "search…"}
              className="w-full rounded-lg border border-line bg-transparent px-2.5 py-1.5 text-sm outline-none"
            />
            {picker.kind !== "item" || (picker.idx ?? 0) < state.items.length ? (
              <button onClick={removeCurrent} className="whitespace-nowrap text-xs text-bad hover:text-bad/80">remove</button>
            ) : null}
            <button onClick={() => setPicker(null)} className="text-xs text-muted hover:text-text">close</button>
          </div>
          <div className="mt-2 grid max-h-44 grid-cols-6 gap-1 overflow-y-auto sm:grid-cols-10">
            {candidates.map((c: any) => (
              <button
                key={c.slug ?? c.name}
                onClick={() => ("cost" in c ? pickItem(c.slug) : pickRune(c.name))}
                title={c.name}
                className="rounded-lg p-1 transition hover:bg-white/[0.08]"
              >
                <img src={c.icon} alt={c.name} width={34} height={34}
                     className={`${"cost" in c ? "rounded-lg" : "rounded-full"} ring-1 ring-white/10`}
                     style={{ width: 34, height: 34 }} />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* champion stats with live deltas as items/runes are added */}
      {m && bareM && (
        <div className="mt-3 border-t border-line/60 pt-3">
          <p className="mb-2 text-[0.6rem] font-bold uppercase tracking-wide text-faint">
            Champion stats <span className="normal-case text-faint/60">· base at level {level}{edited ? " + your items" : ""}</span>
          </p>
          <div className="grid grid-cols-3 gap-x-2 gap-y-3 text-center sm:grid-cols-5">
            <StatDelta label="Attack Damage" v={m.ad} d={m.ad - bareM.ad} cls="text-orange-400" />
            <StatDelta label="Ability Power" v={m.ap} d={m.ap - bareM.ap} cls="text-violet-400" />
            <StatDelta label="Health" v={m.hp} d={m.hp - bareM.hp} cls="text-emerald-300" />
            <StatDelta label="Armor" v={m.armor} d={m.armor - bareM.armor} cls="text-orange-300" />
            <StatDelta label="Magic Resist" v={m.mr} d={m.mr - bareM.mr} cls="text-violet-300" />
            <StatDelta label="Attack Speed" v={m.attackSpeed} d={Math.round((m.attackSpeed - bareM.attackSpeed) * 100) / 100} cls="text-text" />
            <StatDelta label="Crit" v={m.crit} suffix="%" d={m.crit - bareM.crit} cls="text-gold" />
            <StatDelta label="Ability Haste" v={m.haste} d={m.haste - bareM.haste} cls="text-accent" />
            <StatDelta label="Move Speed" v={m.moveSpeed} d={m.moveSpeed - bareM.moveSpeed} cls="text-text" />
            <StatDelta label="Mana" v={m.mana} d={m.mana - bareM.mana} cls="text-blue-300" />
          </div>
        </div>
      )}

      {/* abilities: damage + scaling at this level, with the current stats */}
      {abilities.length > 0 && (
        <div className="mt-3 border-t border-line/60 pt-3">
          <p className="mb-2 text-[0.6rem] font-bold uppercase tracking-wide text-faint">
            Abilities <span className="normal-case text-faint/60">· raw damage at level {level}</span>
          </p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {abilities.map((a) => (
              <div key={a.slot} className="rounded-lg bg-white/[0.04] px-2 py-2">
                <div className="flex items-baseline justify-between">
                  <span className="text-xs font-bold text-text">{SLOT_KEY[a.slot] ?? a.slot} <span className="font-normal text-faint">R{a.rank}</span></span>
                  <span className={`text-sm font-bold ${a.type === "physical" ? "text-orange-400" : a.type === "magic" ? "text-violet-400" : "text-white"}`}>{a.dmg.toLocaleString()}</span>
                </div>
                <div className="truncate text-[0.6rem] text-muted" title={a.name}>{a.name}</div>
                {a.scaling && <div className="text-[0.6rem] text-faint">{a.scaling}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* live verdict */}
      {m && edited && (
        <div className="mt-3 border-t border-line/60 pt-3">
          <div className="grid grid-cols-3 gap-2 text-center sm:grid-cols-6">
            <Live label="3s burst" v={m.burst3.toLocaleString()} cls="text-bad" />
            <Live label="DPS (8s)" v={m.dps8.toLocaleString()} cls="text-accent" />
            <Live label="Kill squishy" v={m.ttk != null ? `${m.ttk.toFixed(2)}s` : ">12s"} cls="text-gold" />
            <Live label="EHP" v={m.ehp.toLocaleString()} cls="text-emerald-300" />
            <Live label="HP / Armor / MR" v={`${m.hp.toLocaleString()} / ${m.armor} / ${m.mr}`} cls="text-text" />
            <Live
              label={baseScore != null ? `score (was ${baseScore})` : "score"}
              v={String(m.score)}
              cls={baseScore != null && m.score >= baseScore ? "text-emerald-300" : "text-bad"}
            />
          </div>
          {style && (
            <p className="mt-2 text-center text-xs text-muted">
              Plays as <span className="font-semibold text-text">{STYLE_LABEL[style.style]}</span>
              {" "}({Math.round(style.autoness * 100)}% auto-reliant) · build around {style.buildHint}
            </p>
          )}
          {issues.length > 0 && (
            <p className="mt-2 text-center text-xs font-medium text-bad">
              ⚠ {issues.join(" · ")}
            </p>
          )}
        </div>
      )}

      {analysis && <SimReadout a={analysis} />}

      {edited && (
        <MonteCarloComparePanel
          name={name}
          current={{ items: allSlugs, runes: runeNames }}
          base={{ items: baseSlugs, runes: baseRunes }}
          currentLabel="Your build"
          baseLabel="Recommended"
        />
      )}
    </div>
  );
}

const STYLE_LABEL: Record<string, string> = {
  "basic-attack": "a basic attacker",
  "ability-caster": "an ability caster",
  hybrid: "a hybrid",
};

function Live({ label, v, cls }: { label: string; v: string; cls: string }) {
  return (
    <div className="rounded-lg bg-white/[0.04] px-2 py-1.5">
      <div className={`text-sm font-bold ${cls}`}>{v}</div>
      <div className="text-[0.6rem] uppercase tracking-wide text-faint">{label}</div>
    </div>
  );
}

const SLOT_KEY: Record<string, string> = { "1": "Q", "2": "W", "3": "E", "4": "R" };

/** A stat with its total and, when the build adds to it, a small ± delta. */
function StatDelta({ label, v, d, cls, suffix = "" }: { label: string; v: number; d: number; cls: string; suffix?: string }) {
  const dr = Math.round(d * 100) / 100;
  return (
    <div>
      <div className={`text-lg font-bold ${cls}`}>
        {v.toLocaleString()}{suffix}
        {dr !== 0 && (
          <span className={`ml-0.5 text-[0.6rem] font-semibold ${dr > 0 ? "text-emerald-300" : "text-bad"}`}>
            {dr > 0 ? "+" : ""}{dr}
          </span>
        )}
      </div>
      <div className="text-[0.55rem] uppercase tracking-wide text-faint">{label}</div>
    </div>
  );
}
