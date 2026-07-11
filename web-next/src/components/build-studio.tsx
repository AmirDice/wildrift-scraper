"use client";

import { useMemo, useState } from "react";
import { buildChampions, buildGold, type Build } from "@/lib/builds";
import { liveMetrics, analyzeBuild } from "@/lib/engine";
import { SimReadout, Tip } from "@/components/build-view";
import { BuildDial } from "@/components/build-dial";
import { BuildCustomizer } from "@/components/build-customizer";
import { EnemyOptimizer } from "@/components/enemy-optimizer";
import { ChampionAvatar, TierChip } from "@/components/ui";
import { FirstVisitGuide } from "@/components/first-visit-guide";

/* eslint-disable @next/next/no-img-element */

const TABS = ["Build", "Analysis", "Customize", "vs Enemy"] as const;
type Tab = (typeof TABS)[number];

const VARIANT_LABEL: Record<string, string> = {
  standard: "Standard", balanced: "Standard", damage: "Damage", dps: "DPS",
  oneshot: "One-shot", burst: "Burst", crit: "Crit", antitank: "Anti-Tank",
  survivability: "Survivability", tanky: "Tanky", sustained: "Sustained",
  battlemage: "Sustained", utility: "Utility", poke: "Poke",
};
const STYLE_LABEL: Record<string, string> = {
  "basic-attack": "Basic attacker", "ability-caster": "Ability caster", hybrid: "Hybrid",
};

function itemsRunes(b: Build) {
  const items = [...b.coreBuild.map((i) => i.slug), ...(b.boots ? [b.boots.slug] : [])];
  const runes = [b.runes.keystone?.name, ...b.runes.treeMinors.map((m) => m.name), b.runes.flexMinor?.name].filter(Boolean) as string[];
  return { items, runes };
}

/** Big friendly headline stat. */
function StatCard({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent: string }) {
  return (
    <div className="rounded-2xl bg-white/[0.04] px-3 py-3 text-center">
      <div className={`text-2xl font-bold ${accent}`}>{value}</div>
      <div className="mt-0.5 text-[0.65rem] uppercase tracking-wide text-faint">{label}</div>
      {sub && <div className="text-[0.6rem] text-muted">{sub}</div>}
    </div>
  );
}

export function BuildStudio() {
  const champs = useMemo(() => buildChampions(), []);
  const [slug, setSlug] = useState(champs[0]?.slug ?? "");
  const [tab, setTab] = useState<Tab>("Build");
  const [level, setLevel] = useState(15);
  const [champQuery, setChampQuery] = useState("");

  const rec = champs.find((c) => c.slug === slug) ?? champs[0];
  const builds = rec.builds;
  const variants = builds.variants?.length ? builds.variants : Object.keys(builds.builds);
  const [variantState, setVariant] = useState(variants.find((v) => v === "standard" || v === "balanced") ?? variants[0]);
  const variant = builds.builds[variantState] ? variantState : variants[0];
  const build = builds.builds[variant];

  const name = rec.champion.name;
  const { items, runes } = itemsRunes(build);
  // Build tab shows the full level-15 build; Analysis has its own level slider.
  const m = useMemo(() => liveMetrics(name, items, runes, variant, 15), [name, items.join(","), runes.join(","), variant]);
  const analysisM = useMemo(() => liveMetrics(name, items, runes, variant, level), [name, items.join(","), runes.join(","), variant, level]);
  const analysis = useMemo(() => analyzeBuild(name, items, runes, level), [name, items.join(","), runes.join(","), level]);
  const style = builds.attackStyle;

  const switchChamp = (s: string) => { setSlug(s); setTab("Build"); };
  const filteredChamps = champQuery
    ? champs.filter((c) => c.champion.name.toLowerCase().includes(champQuery.toLowerCase()))
    : champs;

  return (
    <div>
      <FirstVisitGuide />
      {/* champion search + selector strip */}
      <input
        value={champQuery}
        onChange={(e) => setChampQuery(e.target.value)}
        placeholder="Search champion…"
        className="mb-2 w-full max-w-xs rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
      />
      <div className="-mx-1 flex gap-1.5 overflow-x-auto pb-2">
        {filteredChamps.map((c) => (
          <button
            key={c.slug}
            onClick={() => switchChamp(c.slug)}
            className={`shrink-0 rounded-full p-0.5 transition ${c.slug === slug ? "ring-2 ring-accent" : "opacity-60 hover:opacity-100"}`}
            title={c.champion.name}
          >
            <ChampionAvatar champion={c.champion} size={44} showBadges={false} />
          </button>
        ))}
        {filteredChamps.length === 0 && <span className="py-3 text-sm text-faint">No champion matches.</span>}
      </div>

      {/* champion header with splash-art banner */}
      <div className="relative mt-3 overflow-hidden rounded-2xl border border-line">
        {rec.champion.splash && (
          <>
            <img src={rec.champion.splash} alt="" aria-hidden className="absolute inset-0 h-full w-full object-cover object-top opacity-30" />
            <div className="absolute inset-0 bg-gradient-to-r from-[#070a12] via-[#070a12]/80 to-transparent" />
          </>
        )}
        <div className="relative flex flex-wrap items-center gap-3 p-4">
          <ChampionAvatar champion={rec.champion} size={60} showBadges={false} />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-bold">{name}</h2>
              <TierChip tier={rec.champion.tier} />
              {style && (
                <Tip tip={<><span className="font-bold">{STYLE_LABEL[style.style]}</span><span className="mt-1 block text-muted">Build around {style.buildHint}.</span></>}>
                  <span className="cursor-pointer rounded-md bg-accent/15 px-2 py-0.5 text-xs font-semibold text-accent">{STYLE_LABEL[style.style]}</span>
                </Tip>
              )}
            </div>
            <p className="text-sm text-muted">{builds.class} · {builds.role} · {builds.damageProfile}</p>
          </div>
        </div>
      </div>

      {/* tabs */}
      <div className="mt-4 flex gap-1 overflow-x-auto rounded-xl border border-line bg-white/[0.03] p-1">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-semibold transition ${tab === t ? "bg-accent/20 text-accent" : "text-muted hover:text-text"}`}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {tab === "Build" && <BuildTab {...{ builds, variants, variant, setVariant, build, m }} />}
        {tab === "Analysis" && <AnalysisTab {...{ analysis, m: analysisM, level, setLevel }} />}
        {tab === "Customize" && <BuildCustomizer name={name} data={builds} />}
        {tab === "vs Enemy" && <EnemyOptimizer />}
      </div>
    </div>
  );
}

function LevelSlider({ level, setLevel }: { level: number; setLevel: (n: number) => void }) {
  return (
    <div className="flex items-center gap-3 rounded-xl bg-white/[0.03] px-3 py-2">
      <span className="shrink-0 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Level</span>
      <input type="range" min={1} max={15} value={level} onChange={(e) => setLevel(Number(e.target.value))}
             className="h-1.5 flex-1 cursor-pointer accent-[var(--color-accent)]" aria-label="Champion level" />
      <span className="w-6 shrink-0 text-right text-sm font-bold text-accent">{level}</span>
    </div>
  );
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function BuildTab({ builds, variants, variant, setVariant, build, m }: any) {
  return (
    <div className="flex flex-col gap-4">
      {/* variant pills */}
      <div className="flex flex-wrap gap-1.5">
        {variants.map((v: string) => (
          <button key={v} onClick={() => setVariant(v)}
                  className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${v === variant ? "bg-accent/20 text-accent" : "bg-white/[0.04] text-muted hover:text-text"}`}>
            {VARIANT_LABEL[v] ?? v}
          </button>
        ))}
        <span className="ml-auto self-center rounded-md bg-gold/10 px-2 py-1 text-xs font-semibold text-gold">~{buildGold(build).toLocaleString()}g</span>
      </div>

      {/* headline stats */}
      {m && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <StatCard label="Win Score" value={String(analysisWin(build) ?? m.score)} accent="text-gold" />
          <StatCard label="Kill squishy" value={m.ttk != null ? `${m.ttk.toFixed(1)}s` : ">12s"} accent="text-bad" />
          <StatCard label="Effective HP" value={m.ehp.toLocaleString()} accent="text-emerald-300" />
          <StatCard label="DPS" value={m.dps8.toLocaleString()} accent="text-accent" />
        </div>
      )}

      {/* the build: items */}
      <div className="glass rounded-2xl p-4">
        <p className="mb-3 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Build order <span className="normal-case text-faint/60">· tap for details</span></p>
        <div className="flex flex-wrap items-center gap-2.5">
          {build.coreBuild.map((it: any, i: number) => (
            <Tip key={it.slug} tip={<><span className="font-bold">{it.name}</span><span className="text-gold"> · {it.cost.toLocaleString()}g</span>{it.core && <span className="ml-1 rounded bg-gold/20 px-1 text-[0.6rem] font-bold uppercase text-gold">core</span>}{it.reason && <span className="mt-1 block text-muted">{it.reason}</span>}</>}>
              <span className="relative cursor-pointer">
                <img src={it.icon} alt={it.name} width={46} height={46} className={`rounded-lg ${it.core ? "ring-2 ring-gold" : "ring-1 ring-white/10"}`} />
                <span className="absolute -left-1.5 -top-1.5 grid h-4.5 w-4.5 min-h-[18px] min-w-[18px] place-items-center rounded-full bg-[#0e1322] text-[0.6rem] font-bold text-accent ring-1 ring-line">{i + 1}</span>
              </span>
            </Tip>
          ))}
          {(build.boots || build.enchantment) && <span className="mx-0.5 text-faint">+</span>}
          {build.boots && (
            <Tip tip={<span className="font-bold">{build.boots.name}</span>}><img src={build.boots.icon} alt={build.boots.name} width={40} height={40} className="cursor-pointer rounded-lg ring-1 ring-white/10" /></Tip>
          )}
        </div>

        {/* runes + summoners */}
        <div className="mt-4 flex flex-wrap items-center gap-4 border-t border-line/60 pt-3">
          <div className="flex items-center gap-2">
            {build.runes.keystone && <Tip tip={<span className="font-bold">{build.runes.keystone.name}</span>}><img src={build.runes.keystone.icon} alt="" width={38} height={38} className="cursor-pointer rounded-full ring-1 ring-white/15" /></Tip>}
            {build.runes.treeMinors.map((r: any) => (
              <Tip key={r.name} tip={<span className="font-bold">{r.name}</span>}><img src={r.icon} alt="" width={28} height={28} className="cursor-pointer rounded-full ring-1 ring-white/10" /></Tip>
            ))}
            {build.runes.flexMinor && <Tip tip={<span className="font-bold">{build.runes.flexMinor.name}</span>}><img src={build.runes.flexMinor.icon} alt="" width={28} height={28} className="cursor-pointer rounded-full opacity-90 ring-1 ring-white/10" /></Tip>}
          </div>
          {(build.summoners ?? []).length > 0 && (
            <div className="flex items-center gap-2">
              {build.summoners.map((s: any) => (
                <Tip key={s.name} tip={<span className="font-bold">{s.name}</span>}><img src={s.icon} alt={s.name} width={28} height={28} className="cursor-pointer rounded-md ring-1 ring-white/10" /></Tip>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* dial */}
      {(builds.dial ?? []).length > 0 && (
        <div className="glass rounded-2xl p-4">
          <BuildDial dial={builds.dial} />
        </div>
      )}
    </div>
  );
}

function analysisWin(build: any): number | undefined {
  return build?.analysis?.winScore;
}

function AnalysisTab({ analysis, m, level, setLevel }: any) {
  return (
    <div className="flex flex-col gap-4">
      <LevelSlider level={level} setLevel={setLevel} />
      {analysis && <SimReadout a={analysis} />}
      {/* base stats */}
      {m && (
        <div className="glass rounded-2xl p-4">
          <p className="mb-3 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Champion stats <span className="normal-case text-faint/60">· at level {level}, with this build</span></p>
          <div className="grid grid-cols-3 gap-x-2 gap-y-3 text-center sm:grid-cols-5">
            <Stat label="Attack Damage" v={m.ad} cls="text-orange-400" />
            <Stat label="Ability Power" v={m.ap} cls="text-violet-400" />
            <Stat label="Health" v={m.hp.toLocaleString()} cls="text-emerald-300" />
            <Stat label="Armor" v={m.armor} cls="text-orange-300" />
            <Stat label="Magic Resist" v={m.mr} cls="text-violet-300" />
            <Stat label="Attack Speed" v={m.attackSpeed} cls="text-text" />
            <Stat label="Crit" v={`${m.crit}%`} cls="text-gold" />
            <Stat label="Ability Haste" v={m.haste} cls="text-accent" />
            <Stat label="Move Speed" v={m.moveSpeed} cls="text-text" />
            <Stat label="Mana" v={m.mana.toLocaleString()} cls="text-blue-300" />
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, v, cls }: { label: string; v: string | number; cls: string }) {
  return (
    <div>
      <div className={`text-lg font-bold ${cls}`}>{v}</div>
      <div className="text-[0.55rem] uppercase tracking-wide text-faint">{label}</div>
    </div>
  );
}
