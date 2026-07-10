"use client";

import { useState } from "react";
import type { DialAnchor } from "@/lib/builds";

/* eslint-disable @next/next/no-img-element */

/** Playstyle dial: slider from full damage to full tank, snapping to the
 *  engine-searched anchor builds. Every position shows the mathematically best
 *  build FOR that weighting, with its computed fight stats. */
export function BuildDial({ dial }: { dial: DialAnchor[] }) {
  // anchors arrive damage-first (offense 90 -> 10); slider is tankiness 0..100
  const anchors = [...dial].sort((a, b) => b.offense - a.offense);
  const [idx, setIdx] = useState(Math.floor(anchors.length / 2));
  const a = anchors[idx];
  if (!a) return null;
  const tankiness = 100 - a.offense;

  return (
    <div className="glass rounded-2xl p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">
          Playstyle dial
        </h3>
        <span className="text-xs text-faint">
          engine-searched build for every position
        </span>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <span className="w-16 text-right text-xs font-bold text-bad">Damage</span>
        <input
          type="range"
          min={0}
          max={anchors.length - 1}
          step={1}
          value={idx}
          onChange={(e) => setIdx(Number(e.target.value))}
          className="h-2 flex-1 cursor-pointer accent-[var(--color-accent)]"
          aria-label="Damage to tankiness dial"
        />
        <span className="w-16 text-xs font-bold text-emerald-300">Tank</span>
      </div>
      <p className="mt-1.5 text-center text-xs text-muted">
        <span className="font-bold text-text">{a.offense}%</span> damage ·{" "}
        <span className="font-bold text-text">{tankiness}%</span> tankiness
      </p>

      <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
        {a.items.map((it, i) => (
          <div key={it.slug} className="flex items-center gap-2">
            {i > 0 && <span className="text-faint">›</span>}
            <img
              src={it.icon}
              alt={it.name}
              title={`${it.name} (${it.cost.toLocaleString()}g)`}
              width={40}
              height={40}
              loading="lazy"
              className="rounded-lg ring-1 ring-white/10"
              style={{ width: 40, height: 40 }}
            />
          </div>
        ))}
        {a.boots && (
          <>
            <span className="text-faint">+</span>
            <img
              src={a.boots.icon}
              alt={a.boots.name}
              title={a.boots.name}
              width={40}
              height={40}
              loading="lazy"
              className="rounded-lg ring-1 ring-white/10"
              style={{ width: 40, height: 40 }}
            />
          </>
        )}
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 text-center sm:grid-cols-6">
        <DialStat label="3s burst" v={a.engine.burst3.toLocaleString()} cls="text-bad" />
        <DialStat label="DPS" v={a.engine.dps8.toLocaleString()} cls="text-accent" />
        <DialStat label="EHP" v={a.engine.ehp.toLocaleString()} cls="text-emerald-300" />
        <DialStat label="HP" v={(a.engine.hp ?? 0).toLocaleString()} cls="text-text" />
        <DialStat label="Armor/MR" v={`${a.engine.armor ?? "?"}/${a.engine.mr ?? "?"}`} cls="text-text" />
        <DialStat label="Fight score" v={String(a.engine.score)} cls="text-gold" />
      </div>
      <p className="mt-2 text-center text-[0.65rem] text-faint">
        runes borrowed from the {a.variantRunes} page · {anchors.length} anchor builds
      </p>
    </div>
  );
}

function DialStat({ label, v, cls }: { label: string; v: string; cls: string }) {
  return (
    <div className="rounded-lg bg-white/[0.04] px-2 py-1.5">
      <div className={`text-sm font-bold ${cls}`}>{v}</div>
      <div className="text-[0.6rem] uppercase tracking-wide text-faint">{label}</div>
    </div>
  );
}
