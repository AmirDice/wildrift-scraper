"use client";

import { useMemo, useState } from "react";
import type { Build, ChampionBuilds } from "@/lib/builds";
import { analyzeBuild, attackProfile, buildIssues, engineItems, engineRunes, liveMetrics } from "@/lib/engine";
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

export function BuildCustomizer({ name, data }: { name: string; data: ChampionBuilds }) {
  const variants = data.variants?.length ? data.variants : Object.keys(data.builds);
  const [variant, setVariant] = useState(variants[0]);
  const base = data.builds[variant];
  const [state, setState] = useState(() => fromBuild(base));
  const [picker, setPicker] = useState<{ kind: "item" | "boots" | "keystone" | "minor" | "flex"; idx?: number } | null>(null);
  const [query, setQuery] = useState("");

  const allItems = useMemo(() => engineItems(), []);
  const allRunes = useMemo(() => engineRunes(), []);
  const itemMeta = useMemo(() => new Map(allItems.map((i) => [i.slug, i])), [allItems]);
  const runeMeta = useMemo(() => new Map(allRunes.map((r) => [r.name, r])), [allRunes]);

  const allSlugs = [...state.items, ...(state.boots ? [state.boots] : [])];
  const runeNames = [state.runes.keystone, ...state.runes.minors, state.runes.flex].filter(Boolean);
  const baseState = useMemo(() => fromBuild(base), [base]);
  const baseSlugs = [...baseState.items, ...(baseState.boots ? [baseState.boots] : [])];
  const baseRunes = [baseState.runes.keystone, ...baseState.runes.minors, baseState.runes.flex].filter(Boolean);
  const edited = allSlugs.join(",") !== baseSlugs.join(",") || runeNames.join(",") !== baseRunes.join(",");
  const m = liveMetrics(name, allSlugs, runeNames, variant);
  const style = attackProfile(name, allSlugs, runeNames);
  const analysis = useMemo(
    () => analyzeBuild(name, allSlugs, runeNames),
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
      items[picker?.idx ?? 0] = slug;
      return { ...s, items };
    });
    setPicker(null);
    setQuery("");
  };
  const pickRune = (rn: string) => {
    setState((s) => {
      const r = { ...s.runes };
      if (picker?.kind === "keystone") r.keystone = rn;
      else if (picker?.kind === "flex") r.flex = rn;
      else if (picker?.kind === "minor") {
        const minors = [...r.minors] as RunePick["minors"];
        minors[picker.idx ?? 0] = rn;
        r.minors = minors;
        r.tree = runeMeta.get(rn)?.tree || r.tree;
      }
      return { ...s, runes: r };
    });
    setPicker(null);
    setQuery("");
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
    // tree minor: same tree, correct slot
    return allRunes.filter(
      (r) => r.type === "Minor" && r.tree === state.runes.tree
        && r.slot === (picker.idx ?? 0) + 1 && r.name.toLowerCase().includes(q));
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
          Customize <span className="normal-case text-faint/70">· tap any slot to change it</span>
        </p>
        <div className="flex items-center gap-1.5">
          <select
            value={variant}
            onChange={(e) => reset(e.target.value)}
            className="rounded-lg border border-line bg-[#0e1322] px-2 py-1 text-xs text-muted"
          >
            {variants.map((v) => <option key={v} value={v}>start from {v}</option>)}
          </select>
          <button onClick={() => reset(variant)}
                  className="rounded-lg border border-line px-2 py-1 text-xs text-muted transition hover:text-text">
            reset
          </button>
        </div>
      </div>

      {/* item slots */}
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {state.items.map((slug, i) => (
          <Tile key={`${slug}-${i}`} icon={itemMeta.get(slug)?.icon}
                label={itemMeta.get(slug)?.name ?? "pick"}
                onClick={() => { setPicker({ kind: "item", idx: i }); setQuery(""); }} />
        ))}
        <span className="text-faint">+</span>
        <Tile icon={itemMeta.get(state.boots)?.icon} label={itemMeta.get(state.boots)?.name ?? "boots"}
              size={36} onClick={() => { setPicker({ kind: "boots" }); setQuery(""); }} />
        <span className="mx-1 h-8 w-px bg-line" />
        <Tile icon={runeMeta.get(state.runes.keystone)?.icon} label={state.runes.keystone || "keystone"}
              size={40} round onClick={() => { setPicker({ kind: "keystone" }); setQuery(""); }} />
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

      {/* live verdict */}
      {m && (
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

      <MonteCarloComparePanel
        name={name}
        current={{ items: allSlugs, runes: runeNames }}
        base={{ items: baseSlugs, runes: baseRunes }}
        currentLabel={edited ? "Your build" : "This build"}
        baseLabel={edited ? "Recommended" : "Recommended"}
      />
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
