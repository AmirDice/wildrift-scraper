"use client";

import { useState } from "react";
import type { AttackStyle, Build, BuildItem, ChampionBuilds, Rune } from "@/lib/builds";
import { buildGold } from "@/lib/builds";

/* eslint-disable @next/next/no-img-element */

/** Hover (desktop) / tap (mobile) tooltip. All item & rune explanations live
 *  here so the build itself stays a clean icon strip. */
function Tip({ tip, children }: { tip: React.ReactNode; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onClick={() => setOpen((o) => !o)}
    >
      {children}
      {open && tip && (
        <span className="absolute bottom-full left-1/2 z-30 mb-2 w-52 -translate-x-1/2 rounded-xl border border-line bg-[#0e1322] p-2.5 text-left text-xs leading-snug text-text shadow-2xl">
          {tip}
        </span>
      )}
    </span>
  );
}

function ItemTile({
  it,
  n,
  size = 46,
}: {
  it: BuildItem;
  n?: number;
  size?: number;
}) {
  return (
    <Tip
      tip={
        <>
          <span className="font-bold">{it.name}</span>
          <span className="text-gold"> · {it.cost.toLocaleString()}g</span>
          {it.core && <span className="ml-1 rounded bg-gold/20 px-1 text-[0.6rem] font-bold uppercase text-gold">core</span>}
          {it.reason && <span className="mt-1 block text-muted">{it.reason}</span>}
        </>
      }
    >
      <span className="relative inline-block cursor-pointer">
        <img
          src={it.icon}
          alt={it.name}
          width={size}
          height={size}
          loading="lazy"
          className={`rounded-lg object-cover ${it.core ? "ring-2 ring-gold/70" : "ring-1 ring-white/10"}`}
          style={{ width: size, height: size }}
        />
        {n != null && (
          <span className="absolute -left-1.5 -top-1.5 grid h-4.5 w-4.5 min-h-[18px] min-w-[18px] place-items-center rounded-full bg-[#0e1322] text-[0.6rem] font-bold text-accent ring-1 ring-line">
            {n}
          </span>
        )}
      </span>
    </Tip>
  );
}

function RuneTile({ r, size = 34, label }: { r: Rune; size?: number; label?: string }) {
  return (
    <Tip
      tip={
        <>
          <span className="font-bold">{r.name}</span>
          {r.tree && <span className="text-faint"> · {r.tree}</span>}
          {r.reason && <span className="mt-1 block text-muted">{r.reason}</span>}
        </>
      }
    >
      <span className="flex cursor-pointer flex-col items-center gap-0.5">
        <img
          src={r.icon}
          alt={r.name}
          width={size}
          height={size}
          loading="lazy"
          className="rounded-full ring-1 ring-white/10"
          style={{ width: size, height: size }}
        />
        {label && <span className="text-[0.55rem] uppercase tracking-wide text-faint">{label}</span>}
      </span>
    </Tip>
  );
}

const VARIANT_LABEL: Record<string, string> = {
  balanced: "Balanced", damage: "Damage", oneshot: "One-shot", burst: "Burst",
  crit: "Crit", tanky: "Tanky", battlemage: "Battlemage", utility: "Utility", poke: "Poke",
};
const VARIANT_ACTIVE: Record<string, string> = {
  balanced: "bg-accent/20 text-accent", damage: "bg-bad/20 text-bad",
  oneshot: "bg-bad/20 text-bad", burst: "bg-bad/20 text-bad", crit: "bg-gold/20 text-gold",
  tanky: "bg-blue-400/20 text-blue-300", battlemage: "bg-accent/20 text-accent",
  utility: "bg-emerald-400/20 text-emerald-300", poke: "bg-gold/20 text-gold",
};
const BURST_VARIANTS = new Set(["damage", "oneshot", "burst"]);

const STYLE_META: Record<string, { label: string; cls: string }> = {
  "basic-attack": { label: "Basic attacker", cls: "bg-gold/15 text-gold" },
  "ability-caster": { label: "Ability caster", cls: "bg-accent/15 text-accent" },
  hybrid: { label: "Hybrid", cls: "bg-emerald-400/15 text-emerald-300" },
};

/** Auto-vs-ability lean chip. Icon-first with the "what to build around"
 *  explanation and the engine's confidence tucked into the tooltip. */
function StyleBadge({ style }: { style: AttackStyle }) {
  const meta = STYLE_META[style.style] ?? STYLE_META.hybrid;
  const pct = Math.round(style.autoness * 100);
  return (
    <Tip
      tip={
        <>
          <span className="font-bold">{meta.label}</span>
          <span className="mt-1 block text-muted">Build around {style.buildHint}.</span>
          <span className="mt-1 block text-faint">
            {pct}% auto-reliant (measured {Math.round(style.measuredAutoShare * 100)}%
            {style.asEfficiency != null && `, AS-efficiency ${style.asEfficiency}`}).
          </span>
          {style.dataQuality === "flagged" && (
            <span className="mt-1 block text-bad">Signals disagree · ability formulas may be incomplete.</span>
          )}
        </>
      }
    >
      <span className={`inline-flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 font-medium ${meta.cls}`}>
        {meta.label}
      </span>
    </Tip>
  );
}

export function BuildView({ data }: { data: ChampionBuilds }) {
  const variants = data.variants?.length ? data.variants : Object.keys(data.builds);
  const [tab, setTab] = useState<string>(
    variants.includes("balanced") ? "balanced" : variants[0]
  );
  const build: Build | undefined = data.builds[tab];
  if (!build) return null;
  const r = build.runes;

  return (
    <div>
      {/* variant toggle */}
      <div className="inline-flex flex-wrap gap-1 rounded-xl border border-line bg-white/[0.03] p-1">
        {variants.map((v) => (
          <button
            key={v}
            onClick={() => setTab(v)}
            className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
              tab === v ? VARIANT_ACTIVE[v] ?? "bg-accent/20 text-accent" : "text-muted hover:text-text"
            }`}
          >
            {VARIANT_LABEL[v] ?? v}
          </button>
        ))}
      </div>

      {/* one-line context: gold, summoners, one-shot flag */}
      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-md bg-white/[0.06] px-2 py-1 font-medium text-gold">
          ~{buildGold(build).toLocaleString()}g
        </span>
        {data.attackStyle && <StyleBadge style={data.attackStyle} />}
        {(build.summoners ?? []).map((s) => (
          <Tip key={s.name} tip={<><span className="font-bold">{s.name}</span>{s.reason && <span className="mt-1 block text-muted">{s.reason}</span>}</>}>
            <span className="inline-flex cursor-pointer items-center gap-1.5 rounded-md bg-white/[0.06] px-2 py-1 font-medium">
              <img src={s.icon} alt="" width={16} height={16} className="h-4 w-4 rounded" />
              {s.name}
            </span>
          </Tip>
        ))}
        {data.canOneshot && BURST_VARIANTS.has(tab) && (
          <span className="rounded-md bg-bad/15 px-2 py-1 font-medium text-bad">can one-shot</span>
        )}
      </div>

      {/* engine card FIRST: the computed verdict is the headline */}
      {build.engine && (
        <div className="glass mt-5 rounded-2xl p-4">
          <p className="mb-3 text-[0.65rem] font-bold uppercase tracking-wide text-faint">
            Engine · computed fight value
          </p>
          <div className="grid grid-cols-3 gap-2 text-center sm:grid-cols-6">
            <Metric label="3s burst" v={build.engine.burst3.toLocaleString()} cls="text-bad" />
            <Metric label="DPS (8s)" v={build.engine.dps8.toLocaleString()} cls="text-accent" />
            <Metric label="Kill squishy" v={build.engine.ttk != null ? `${build.engine.ttk.toFixed(2)}s` : ">12s"} cls="text-gold" />
            <Metric label="EHP" v={build.engine.ehp.toLocaleString()} cls="text-emerald-300" />
            <Metric label="Sustain" v={(build.engine.sustain ?? 0).toLocaleString()} cls="text-emerald-300" />
            <Metric label="Fight score" v={String(build.engine.score)} cls="text-text" />
          </div>
          {build.engine.ad != null && (
            <div className="mt-3 grid grid-cols-5 gap-x-2 gap-y-2 border-t border-line/60 pt-3 text-center sm:grid-cols-10">
              <Metric small label="AD" v={String(build.engine.ad)} />
              <Metric small label="AP" v={String(build.engine.ap ?? 0)} />
              <Metric small label="HP" v={(build.engine.hp ?? 0).toLocaleString()} />
              <Metric small label="Armor" v={String(build.engine.armor ?? "-")} />
              <Metric small label="MR" v={String(build.engine.mr ?? "-")} />
              <Metric small label="MS" v={String(build.engine.moveSpeed ?? "-")} />
              <Metric small label="AS" v={String(build.engine.attackSpeed ?? "-")} />
              <Metric small label="Haste" v={String(build.engine.haste ?? "-")} />
              <Metric small label="Crit" v={`${build.engine.crit ?? 0}%`} />
              <Metric small label="Mana" v={(build.engine.mana ?? 0).toLocaleString()} />
            </div>
          )}
        </div>
      )}

      {build.analysis && <SimReadout a={build.analysis} />}

      <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_320px]">
        {/* left: items */}
        <div className="flex flex-col gap-5">
          {/* build order: pure icon strip, everything else in tooltips */}
          <div className="glass rounded-2xl p-4">
            <p className="mb-3 text-[0.65rem] font-bold uppercase tracking-wide text-faint">
              Build order <span className="normal-case text-faint/70">· core items first · hover or tap</span>
            </p>
            <div className="flex flex-wrap items-center gap-2.5">
              {build.coreBuild.map((it, i) => (
                <ItemTile key={it.slug} it={it} n={i + 1} />
              ))}
              {(build.boots || build.enchantment) && <span className="mx-0.5 text-faint">+</span>}
              {build.boots && <ItemTile it={build.boots} size={40} />}
              {build.enchantment && <ItemTile it={build.enchantment} size={40} />}
            </div>
          </div>

          {/* situational: horizontal chips, one per threat */}
          {(build.situational.length > 0 || (build.situationalRunes ?? []).length > 0) && (
            <div className="glass rounded-2xl p-4">
              <p className="mb-3 text-[0.65rem] font-bold uppercase tracking-wide text-faint">
                Situational
              </p>
              <div className="flex flex-wrap gap-2.5">
                {build.situational.map((s) => {
                  const replaced = s.replaces
                    ? build.coreBuild.find((c) => c.slug === s.replaces)
                    : undefined;
                  return (
                    <div key={s.slug} className="flex flex-col items-center gap-1.5 rounded-xl bg-white/[0.04] px-3 py-2">
                      <span className="text-[0.6rem] font-bold uppercase tracking-wide text-muted">
                        {s.when || "swap"}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <ItemTile it={s} size={34} />
                        {replaced && (
                          <>
                            <span className="text-xs text-faint">→</span>
                            <span className="opacity-50">
                              <ItemTile it={replaced} size={34} />
                            </span>
                          </>
                        )}
                      </span>
                    </div>
                  );
                })}
                {(build.situationalRunes ?? []).map((s) => (
                  <div key={s.slug} className="flex flex-col items-center gap-1.5 rounded-xl bg-white/[0.04] px-3 py-2">
                    <span className="text-[0.6rem] font-bold uppercase tracking-wide text-muted">
                      {s.when || "runes"}
                    </span>
                    <RuneTile r={{ ...s, tree: "", reason: s.replaces ? `in for ${s.replaces}` : "" }} size={30} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* why this works, kept short */}
          {(data.synergyNotes ?? []).length > 0 && (
            <div className="glass rounded-2xl border-l-2 border-accent/60 p-4">
              <p className="text-[0.65rem] font-bold uppercase tracking-wide text-accent">Why this works</p>
              <ul className="mt-1.5 flex flex-col gap-1">
                {data.synergyNotes!.map((n) => (
                  <li key={n} className="text-xs leading-relaxed text-muted">{n}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* right: rune page as icons */}
        <div className="glass h-fit rounded-2xl p-4">
          <p className="mb-3 text-[0.65rem] font-bold uppercase tracking-wide text-faint">
            Runes <span className="normal-case text-faint/70">· {r.primaryTree}</span>
          </p>
          <div className="flex items-center justify-center gap-4">
            {r.keystone && <RuneTile r={{ ...r.keystone, tree: "" }} size={52} label="keystone" />}
            <span className="h-10 w-px bg-line" />
            {r.treeMinors.map((m) => (
              <RuneTile key={m.slug} r={m} size={36} />
            ))}
            {r.flexMinor && (
              <>
                <span className="h-10 w-px bg-line" />
                <RuneTile r={r.flexMinor} size={36} label="flex" />
              </>
            )}
          </div>
          {r.keystone && (
            <p className="mt-3 text-center text-sm font-semibold">{r.keystone.name}</p>
          )}
          <p className="mt-1 text-center text-xs text-muted">
            {r.treeMinors.map((m) => m.name).join(" · ")}
            {r.flexMinor ? ` + ${r.flexMinor.name}` : ""}
          </p>
        </div>
      </div>
    </div>
  );
}

const TTK_ORDER: { key: string; label: string }[] = [
  { key: "adc", label: "ADC" }, { key: "mage", label: "Mage" },
  { key: "fighter", label: "Fighter" }, { key: "bruiser", label: "Bruiser" },
  { key: "tank", label: "Tank" },
];

function fmtTtk(v: number | null | undefined) {
  return v == null ? ">15s" : `${v.toFixed(2)}s`;
}

/** Section label used across the simulator readout. */
function SubHead({ children }: { children: React.ReactNode }) {
  return <p className="mb-2 text-[0.6rem] font-bold uppercase tracking-wide text-faint">{children}</p>;
}

/** Full multi-dimensional simulator readout: damage composition, TTK across
 *  target types, gold efficiency, mitigation and real-fight friction. */
export function SimReadout({ a }: { a: import("@/lib/builds").BuildAnalysis }) {
  const typeSeg = [
    { label: "Physical", v: a.byTypePct.physical, cls: "bg-gold" },
    { label: "Magic", v: a.byTypePct.magic, cls: "bg-accent" },
    { label: "True", v: a.byTypePct.true, cls: "bg-white/70" },
  ].filter((s) => s.v > 0);
  const srcTotal = Math.max(1, a.bySource.auto + a.bySource.ability);
  const autoPct = Math.round((a.bySource.auto / srcTotal) * 100);

  return (
    <div className="glass mt-4 rounded-2xl p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Simulator readout</p>
        <Tip tip={<span className="text-muted">Class-weighted composite of TTK, DPS, burst, survivability and healing.</span>}>
          <span className="cursor-pointer rounded-md bg-gold/15 px-2 py-1 text-xs font-bold text-gold">
            Win Score {a.winScore} <span className="font-normal text-gold/70">· {a.preset}</span>
          </span>
        </Tip>
      </div>

      {/* time to kill each target type */}
      <SubHead>Time to kill by target</SubHead>
      <div className="mb-4 grid grid-cols-5 gap-2 text-center">
        {TTK_ORDER.map((t) => (
          <div key={t.key} className="rounded-lg bg-white/[0.04] px-1.5 py-1.5">
            <div className="text-sm font-bold text-gold">{fmtTtk(a.ttk[t.key])}</div>
            <div className="text-[0.55rem] uppercase tracking-wide text-faint">{t.label}</div>
          </div>
        ))}
      </div>

      {/* damage composition: type + source bars */}
      <div className="mb-4 grid gap-4 sm:grid-cols-2">
        <div>
          <SubHead>Damage by type</SubHead>
          <div className="flex h-3 overflow-hidden rounded-full bg-white/5">
            {typeSeg.map((s) => (
              <div key={s.label} className={s.cls} style={{ width: `${s.v}%` }} title={`${s.label} ${s.v}%`} />
            ))}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[0.65rem] text-muted">
            {typeSeg.map((s) => <span key={s.label}>{s.label} {s.v}%</span>)}
          </div>
        </div>
        <div>
          <SubHead>Auto vs ability</SubHead>
          <div className="flex h-3 overflow-hidden rounded-full bg-white/5">
            <div className="bg-gold" style={{ width: `${autoPct}%` }} title={`Autos ${autoPct}%`} />
            <div className="bg-accent" style={{ width: `${100 - autoPct}%` }} title={`Abilities ${100 - autoPct}%`} />
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-3 text-[0.65rem] text-muted">
            <span>Autos {autoPct}%</span><span>Abilities {100 - autoPct}%</span>
          </div>
        </div>
      </div>

      {/* gold efficiency + mitigation + friction */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        <div>
          <SubHead>Gold efficiency</SubHead>
          <p className="text-xs text-text">{a.goldEff.gold.toLocaleString()}g total</p>
          {a.goldEff.dmgPerGold != null && <p className="text-xs text-muted">{a.goldEff.dmgPerGold} dmg/g</p>}
          {a.goldEff.ehpPerGold != null && <p className="text-xs text-muted">{a.goldEff.ehpPerGold} EHP/g</p>}
        </div>
        <div>
          <SubHead>Effective HP</SubHead>
          <p className="text-xs text-text">{a.ehpSplit.physical.toLocaleString()} vs AD</p>
          <p className="text-xs text-muted">{a.ehpSplit.magic.toLocaleString()} vs AP</p>
        </div>
        <div>
          <SubHead>Mitigation</SubHead>
          <p className="text-xs text-text">{a.damagePrevented.total.toLocaleString()} prevented</p>
          {a.shields.value > 0 && <p className="text-xs text-muted">{a.shields.value.toLocaleString()} shield</p>}
          {a.healing.total > 0 && <p className="text-xs text-muted">{a.healing.total.toLocaleString()} healed</p>}
        </div>
        <div>
          <SubHead>Real-fight friction</SubHead>
          <p className="text-xs text-text">{a.cooldownUtil.efficiency}% cd used</p>
          <p className="text-xs text-muted">{a.damageLost.autoUptimePct}% auto uptime</p>
          {a.damageLost.overkill > 0 && <p className="text-xs text-muted">{a.damageLost.overkill.toLocaleString()} overkill</p>}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, v, cls = "text-text", small = false }: { label: string; v: string; cls?: string; small?: boolean }) {
  return (
    <div className={small ? "" : "rounded-lg bg-white/[0.04] px-2 py-1.5"}>
      <div className={`${small ? "text-sm" : "text-sm"} font-bold ${cls}`}>{v}</div>
      <div className="text-[0.6rem] uppercase tracking-wide text-faint">{label}</div>
    </div>
  );
}
