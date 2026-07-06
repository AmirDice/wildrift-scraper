"use client";

import { useState } from "react";
import type { Build, ChampionBuilds } from "@/lib/builds";
import { buildGold } from "@/lib/builds";

/* eslint-disable @next/next/no-img-element */

function ItemIcon({ src, alt, size = 48 }: { src: string; alt: string; size?: number }) {
  return (
    <img
      src={src}
      alt={alt}
      width={size}
      height={size}
      loading="lazy"
      className="rounded-lg object-cover ring-1 ring-white/10"
      style={{ width: size, height: size }}
    />
  );
}

function BuildOrder({ build }: { build: Build }) {
  return (
    <div className="flex flex-col gap-2.5">
      {build.coreBuild.map((it, i) => (
        <div key={it.slug} className="glass flex items-center gap-3 rounded-xl p-2.5">
          <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-accent/15 text-xs font-bold text-accent">
            {i + 1}
          </span>
          <ItemIcon src={it.icon} alt={it.name} />
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate font-semibold">{it.name}</span>
              <span className="shrink-0 text-xs font-medium text-gold">{it.cost.toLocaleString()}g</span>
            </div>
            {it.reason && <p className="mt-0.5 text-xs leading-snug text-muted">{it.reason}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

function Runes({ build }: { build: Build }) {
  const r = build.runes;
  return (
    <div className="glass rounded-2xl p-5">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">Runes</h3>
      {r.keystone && (
        <div className="mt-3 flex items-center gap-3">
          <ItemIcon src={r.keystone.icon} alt={r.keystone.name} size={52} />
          <div>
            <div className="text-[0.7rem] font-bold uppercase tracking-wide text-accent">Keystone</div>
            <div className="font-semibold">{r.keystone.name}</div>
            {r.keystone.reason && <p className="text-xs text-muted">{r.keystone.reason}</p>}
          </div>
        </div>
      )}
      <div className="mt-4 text-[0.7rem] font-bold uppercase tracking-wide text-faint">
        {r.primaryTree} tree
      </div>
      <div className="mt-2 flex flex-col gap-2">
        {r.treeMinors.map((m) => (
          <div key={m.slug} className="flex items-center gap-2.5">
            <ItemIcon src={m.icon} alt={m.name} size={32} />
            <div className="min-w-0">
              <span className="text-sm font-medium">{m.name}</span>
              {m.reason && <span className="ml-1.5 text-xs text-muted">· {m.reason}</span>}
            </div>
          </div>
        ))}
      </div>
      {r.flexMinor && (
        <>
          <div className="mt-4 text-[0.7rem] font-bold uppercase tracking-wide text-faint">
            Flex ({r.flexMinor.tree})
          </div>
          <div className="mt-2 flex items-center gap-2.5">
            <ItemIcon src={r.flexMinor.icon} alt={r.flexMinor.name} size={32} />
            <span className="text-sm font-medium">{r.flexMinor.name}</span>
          </div>
        </>
      )}
    </div>
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

export function BuildView({ data }: { data: ChampionBuilds }) {
  const variants = data.variants?.length ? data.variants : Object.keys(data.builds);
  const [tab, setTab] = useState<string>(
    variants.includes("balanced") ? "balanced" : variants[0]
  );
  const build = data.builds[tab];
  if (!build) return null;

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

      <p className="mt-4 max-w-2xl text-sm text-muted">{build.summary}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-md bg-white/[0.06] px-2 py-1 font-medium text-gold">
          ~{buildGold(build).toLocaleString()}g full build
        </span>
        {data.canOneshot && BURST_VARIANTS.has(tab) && (
          <span className="rounded-md bg-bad/15 px-2 py-1 font-medium text-bad">can one-shot squishies</span>
        )}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_340px]">
        {/* items */}
        <div>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">
            Build order
          </h3>
          <BuildOrder build={build} />

          {/* boots + enchant */}
          <div className="mt-4 grid grid-cols-2 gap-3">
            {build.boots && (
              <div className="glass flex items-center gap-3 rounded-xl p-2.5">
                <ItemIcon src={build.boots.icon} alt={build.boots.name} size={40} />
                <div className="min-w-0">
                  <div className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Boots</div>
                  <div className="truncate text-sm font-semibold">{build.boots.name}</div>
                </div>
              </div>
            )}
            {build.enchantment && (
              <div className="glass flex items-center gap-3 rounded-xl p-2.5">
                <ItemIcon src={build.enchantment.icon} alt={build.enchantment.name} size={40} />
                <div className="min-w-0">
                  <div className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Enchant</div>
                  <div className="truncate text-sm font-semibold">{build.enchantment.name}</div>
                </div>
              </div>
            )}
          </div>

          {/* situational */}
          {build.situational.length > 0 && (
            <div className="mt-5">
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">
                Situational swaps
              </h3>
              <div className="flex flex-col gap-2">
                {build.situational.map((s) => (
                  <div key={s.slug} className="flex items-center gap-2.5 text-sm">
                    <ItemIcon src={s.icon} alt={s.name} size={30} />
                    <span className="font-medium">{s.name}</span>
                    {s.when && <span className="text-xs text-muted">— {s.when}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* runes */}
        <Runes build={build} />
      </div>
    </div>
  );
}
