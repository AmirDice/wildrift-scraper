"use client";

import { useMemo, useState } from "react";
import { rosterList, threatProfile, counterSwaps } from "@/lib/threat";
import { engineItems } from "@/lib/engine";
import { buildChampions, type Build } from "@/lib/builds";

/* eslint-disable @next/next/no-img-element */

const SLOTS = 5;

/** Champion portrait with a letter fallback when the roster has no icon URL. */
function ChampIcon({ name, icon, size, className = "" }: { name: string; icon: string; size: number; className?: string }) {
  if (icon) return <img src={icon} alt={name} title={name} width={size} height={size} className={className} />;
  return (
    <span
      title={name}
      className={`grid place-items-center bg-white/10 font-bold text-faint ${className}`}
      style={{ width: size, height: size, fontSize: size * 0.4 }}
    >
      {name.slice(0, 2)}
    </span>
  );
}

function buildLists(b: Build): { items: string[]; runes: string[]; core: string[] } {
  const items = b.coreBuild.map((i) => i.slug);
  if (b.boots) items.push(b.boots.slug);
  const core = b.coreBuild.filter((i) => i.core).map((i) => i.slug);
  const runes = [
    b.runes.keystone?.name,
    ...b.runes.treeMinors.map((m) => m.name),
    b.runes.flexMinor?.name,
  ].filter(Boolean) as string[];
  return { items, runes, core };
}

/** Enemy-team optimizer: pick the enemy comp, see its threat profile and the
 *  situational counters that beat it, grounded in the enemy champions' own
 *  damage types, kits and base stats. */
export function EnemyOptimizer() {
  const all = useMemo(() => rosterList(), []);
  const items = useMemo(() => new Map(engineItems().map((i) => [i.slug, i])), []);
  const myChamps = useMemo(() => buildChampions(), []);
  const [mine, setMine] = useState(myChamps[0]?.champion.name ?? "");
  const [mineOpen, setMineOpen] = useState(false);
  const [mineQuery, setMineQuery] = useState("");
  const [picks, setPicks] = useState<(string | null)[]>(Array(SLOTS).fill(null));
  const [open, setOpen] = useState<number | null>(null);
  const [query, setQuery] = useState("");

  const myRec = myChamps.find((c) => c.champion.name === mine);
  const myRole = myRec?.builds.role ?? "";
  const chosen = picks.filter(Boolean) as string[];
  const threat = useMemo(() => (chosen.length ? threatProfile(chosen, 13, myRole) : null), [chosen.join(","), myRole]);

  const myBuild = useMemo(() => {
    if (!myRec) return null;
    const variant = myRec.builds.variants.find((v) => myRec.builds.builds[v]) ?? "";
    const b = myRec.builds.builds[variant];
    return b ? { name: mine, variant, ...buildLists(b) } : null;
  }, [mine, myRec]);

  const swaps = useMemo(
    () => (threat && myBuild ? counterSwaps(myBuild.name, myBuild.items, myBuild.runes, threat, 15, myBuild.core) : []),
    [threat, myBuild],
  );

  const filtered = query
    ? all.filter((c) => c.name.toLowerCase().includes(query.toLowerCase()))
    : all;

  const pick = (slot: number, name: string) => {
    setPicks((p) => { const n = [...p]; n[slot] = name; return n; });
    setOpen(null); setQuery("");
  };

  return (
    <div className="glass rounded-2xl p-4">
      <p className="mb-3 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Enemy team optimizer</p>

      {/* your champion: searchable portrait picker */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative">
          <p className="mb-1 text-[0.6rem] font-bold uppercase tracking-wide text-faint">Your champion</p>
          <button
            onClick={() => { setMineOpen((o) => !o); setMineQuery(""); }}
            className="flex items-center gap-2 rounded-xl border border-accent/40 bg-accent/5 px-2 py-1.5 transition hover:border-accent/60"
          >
            {myRec && <ChampIcon name={myRec.champion.name} icon={myRec.champion.icon} size={36} className="rounded-lg" />}
            <span className="pr-1 text-sm font-semibold text-text">{mine}</span>
            <span className="text-faint">▾</span>
          </button>
          {mineOpen && (
            <div className="absolute z-30 mt-1 w-60 rounded-xl border border-line bg-[#0e1322] p-2 shadow-2xl">
              <input autoFocus value={mineQuery ?? ""} onChange={(e) => setMineQuery(e.target.value)}
                     placeholder="Search your champion…"
                     className="mb-2 w-full rounded-md border border-line bg-white/[0.04] px-2 py-1.5 text-xs text-text outline-none" />
              <div className="max-h-60 overflow-y-auto">
                {myChamps.filter((c) => c.champion.name.toLowerCase().includes(mineQuery.toLowerCase())).map((c) => (
                  <button key={c.slug} onClick={() => { setMine(c.champion.name); setMineOpen(false); }}
                          className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-xs text-text hover:bg-white/[0.06]">
                    <ChampIcon name={c.champion.name} icon={c.champion.icon} size={24} className="rounded" />
                    <span>{c.champion.name}</span>
                    <span className="ml-auto text-[0.6rem] text-faint">{c.builds.role}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
      <p className="mb-3 text-xs text-muted">Now pick the enemy champions to see the threat profile and the engine-scored item swaps that counter this specific comp.</p>

      {/* enemy slots */}
      <div className="flex flex-wrap gap-2">
        {picks.map((name, i) => {
          const c = name ? all.find((x) => x.name === name) : null;
          return (
            <div key={i} className="relative">
              <button
                onClick={() => { setOpen(open === i ? null : i); setQuery(""); }}
                className={`flex h-14 w-14 items-center justify-center rounded-xl border ${
                  c ? "border-accent/40 bg-accent/5" : "border-line border-dashed bg-white/[0.02]"
                } transition hover:border-accent/60`}
              >
                {c ? (
                  <ChampIcon name={c.name} icon={c.icon} size={44} className="rounded-lg" />
                ) : (
                  <span className="text-xl text-faint">+</span>
                )}
              </button>
              {name && (
                <button
                  onClick={() => setPicks((p) => { const n = [...p]; n[i] = null; return n; })}
                  className="absolute -right-1 -top-1 grid h-4 w-4 place-items-center rounded-full bg-bad/80 text-[0.6rem] font-bold text-white"
                  aria-label="remove"
                >×</button>
              )}
              {open === i && (
                <div className="absolute z-30 mt-1 w-56 rounded-xl border border-line bg-[#0e1322] p-2 shadow-2xl">
                  <input
                    autoFocus
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search champion…"
                    className="mb-2 w-full rounded-md border border-line bg-white/[0.04] px-2 py-1.5 text-xs text-text outline-none"
                  />
                  <div className="max-h-56 overflow-y-auto">
                    {filtered.slice(0, 40).map((c) => (
                      <button
                        key={c.slug}
                        onClick={() => pick(i, c.name)}
                        className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-xs text-text hover:bg-white/[0.06]"
                      >
                        <ChampIcon name={c.name} icon={c.icon} size={24} className="rounded" />
                        <span>{c.name}</span>
                        <span className="ml-auto text-[0.6rem] text-faint">{c.class}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {threat && (
        <div className="mt-4">
          {/* threat profile */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
            <div>
              <p className="mb-1 text-[0.6rem] font-bold uppercase tracking-wide text-faint">Damage split</p>
              <div className="flex h-3 overflow-hidden rounded-full bg-white/5">
                <div className="bg-orange-500" style={{ width: `${threat.adShare * 100}%` }} title={`AD ${Math.round(threat.adShare * 100)}%`} />
                <div className="bg-violet-500" style={{ width: `${threat.apShare * 100}%` }} title={`AP ${Math.round(threat.apShare * 100)}%`} />
              </div>
              <p className="mt-1 text-[0.65rem]"><span className="text-orange-400">AD {Math.round(threat.adShare * 100)}%</span> · <span className="text-violet-400">AP {Math.round(threat.apShare * 100)}%</span></p>
            </div>
            <div>
              <p className="mb-1 text-[0.6rem] font-bold uppercase tracking-wide text-faint">Frontline</p>
              <p className="text-xs text-text">{threat.frontline.name}</p>
              <p className="text-[0.65rem] text-muted">{threat.frontline.hp} HP · {threat.frontline.armor}/{threat.frontline.mr}</p>
            </div>
            <div>
              <p className="mb-1 text-[0.6rem] font-bold uppercase tracking-wide text-faint">Primary carry</p>
              <p className="text-xs text-text">{threat.carry.name}</p>
              <p className="text-[0.65rem] text-muted">{threat.carry.hp} HP · {threat.carry.armor}/{threat.carry.mr}</p>
            </div>
            <div>
              <p className="mb-1 text-[0.6rem] font-bold uppercase tracking-wide text-faint">Threats</p>
              <p className="text-[0.65rem] text-muted">
                {threat.ccCount} CC · {threat.healers.length} heal · {threat.shielders.length} shield
                {threat.assassins.length > 0 && ` · ${threat.assassins.length} assassin`}
              </p>
              {threat.laneOpponent && (
                <p className="mt-0.5 text-[0.65rem] text-muted">Lane: <span className="font-semibold text-text">{threat.laneOpponent}</span> <span className="text-faint">(weighted)</span></p>
              )}
            </div>
          </div>

          {/* engine-scored counter swaps for the chosen champion's build */}
          <p className="mb-2 mt-4 text-[0.6rem] font-bold uppercase tracking-wide text-faint">
            Counter swaps for {myBuild?.name}
            {myBuild && <span className="ml-1 normal-case text-faint/70">· {myBuild.variant} build</span>}
          </p>
          {swaps.length === 0 && (
            <p className="text-xs text-muted">
              No swap improves this build against this comp — your standard items already hold up.
            </p>
          )}
          <div className="space-y-2">
            {swaps.map((r) => {
              const s = r.swap!;
              const add = items.get(s.add), rem = items.get(s.remove);
              return (
                <div key={r.key} className="rounded-xl bg-white/[0.03] p-2.5">
                  <div className="flex items-center gap-2.5">
                    {rem && <img src={rem.icon} alt={rem.name} title={rem.name} className="h-9 w-9 rounded-md opacity-40 grayscale ring-1 ring-line" />}
                    <span className="text-faint">→</span>
                    {add && <img src={add.icon} alt={add.name} title={add.name} className="h-9 w-9 rounded-md ring-2 ring-emerald-400/50" />}
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-text">
                        {s.addName} <span className="font-normal text-muted">over {s.removeName}</span>
                      </p>
                      <p className="text-[0.65rem] text-muted">{r.label} · {r.reason}</p>
                    </div>
                    <span className="ml-auto shrink-0 rounded-md bg-emerald-400/15 px-2 py-1 text-xs font-bold text-emerald-300">
                      +{s.delta.toFixed(1)}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-0.5 pl-[3.1rem] text-[0.65rem] text-muted">
                    <span>EHP vs comp <span className="text-text">{s.ehpBefore.toLocaleString()}</span> → <span className="font-semibold text-emerald-300">{s.ehpAfter.toLocaleString()}</span></span>
                    <span>Kill their {threat.carry.name} <span className="text-text">{s.ttkBefore != null ? `${s.ttkBefore.toFixed(2)}s` : ">15s"}</span> → <span className="text-text">{s.ttkAfter != null ? `${s.ttkAfter.toFixed(2)}s` : ">15s"}</span></span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
