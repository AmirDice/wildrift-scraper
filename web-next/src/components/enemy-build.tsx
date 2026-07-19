"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { rosterList } from "@/lib/threat";
import engineData from "@/data/engine.json";

/* eslint-disable @next/next/no-img-element */

// item/boot icons were rehosted to /items/<slug>.webp; runes carry their own.
const DATA = engineData as any;
const itemName = (slug: string): string => DATA.items?.[slug]?.name ?? slug;
const itemCost = (slug: string): number => DATA.items?.[slug]?.cost ?? 0;
// use the STORED icon, not `/items/<slug>.webp`: aliased items (Lord Dominik's
// Regard) keep the source file name (dominiks-regards.webp), so constructing
// the path from the canonical slug 404s.
const itemIcon = (slug: string): string => DATA.items?.[slug]?.icon ?? `/items/${slug}.webp`;
const runeIcon = (name: string): string | null => DATA.runes?.[name]?.icon ?? null;

const PLAYSTYLES = [
  ["standard", "Standard"], ["damage", "Damage"], ["crit", "Crit"],
  ["dps", "On-hit / DPS"], ["burst", "Burst"], ["oneshot", "One-shot"],
  ["splitpush", "Split-push"], ["kiting", "Kiting"], ["vamp", "Lifesteal"],
  ["antitank", "Anti-tank"], ["tanky", "Bruiser"], ["poke", "Poke"],
  ["utility", "Utility"],
] as const;

// Orthogonal optimization axis, sent alongside the playstyle.
const OBJECTIVES = [
  ["balanced", "Balanced"], ["maxstats", "Max stats"], ["maxsynergy", "Max synergy"],
] as const;

const ROLES = ["Baron", "Jungle", "Mid", "Dragon", "Support"] as const;

/** Sparkles mark (Heroicons) on the generate buttons: the visual cue for a
 *  generated build. */
export function Sparkles({ className = "", size = 14 }: { className?: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
      <path d="M18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
      <path d="M16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
    </svg>
  );
}

type Advice = {
  items?: string[];
  boots?: string;
  bootsUpgrade?: string;
  runes?: { keystone: string; primaryTree: string; minors: string[]; flex: string };
  situational?: { item: string; when: string; replaces: string }[];
  why?: string[];
  engineScore?: number | null;
  validationErrors?: string[];
  error?: string;
};

function ChampIcon({ name, icon, size }: { name: string; icon: string; size: number }) {
  if (icon) return <img src={icon} alt={name} title={name} width={size} height={size} className="rounded-md object-cover" style={{ width: size, height: size }} />;
  return (
    <span title={name} className="grid place-items-center rounded-md bg-white/10 font-bold text-faint"
      style={{ width: size, height: size, fontSize: size * 0.38 }}>
      {name.slice(0, 2)}
    </span>
  );
}

/** Searchable champion picker used for both "my champion" and enemy slots. */
function Picker({ value, onPick, placeholder, size = 44 }: {
  value: string | null; onPick: (name: string) => void; placeholder: string; size?: number;
}) {
  const all = useMemo(() => rosterList(), []);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const picked = value ? all.find((c) => c.name === value) : null;
  const results = q ? all.filter((c) => c.name.toLowerCase().includes(q.toLowerCase())).slice(0, 8) : all.slice(0, 8);

  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-lg border border-line bg-white/[0.03] px-2 py-1.5 text-sm transition hover:border-accent/50"
        style={{ minWidth: size + 90 }}>
        {picked ? <ChampIcon name={picked.name} icon={picked.icon} size={size} /> :
          <span className="grid place-items-center rounded-md bg-white/5 text-faint" style={{ width: size, height: size }}>+</span>}
        <span className={picked ? "font-medium" : "text-faint"}>{picked?.name ?? placeholder}</span>
      </button>
      {open && (
        <div className="absolute z-30 mt-1 w-56 rounded-xl border border-line bg-[#0e1322] p-2 shadow-2xl">
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search…"
            className="mb-2 w-full rounded-md border border-line bg-white/5 px-2 py-1 text-sm outline-none" />
          <div className="max-h-64 overflow-y-auto">
            {results.map((c) => (
              <button key={c.name} onClick={() => { onPick(c.name); setOpen(false); setQ(""); }}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-white/5">
                <ChampIcon name={c.name} icon={c.icon} size={26} />
                <span>{c.name}</span>
                <span className="ml-auto text-[0.65rem] text-faint">{c.role}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ItemStrip({ advice }: { advice: Advice }) {
  const items = advice.items ?? [];
  const upAfter = 2; // tier-3 lands after ~2 items (matches the advisor's guidance)
  return (
    <div className="flex flex-wrap items-center gap-2.5">
      {advice.boots && (
        <span className="relative inline-flex flex-col items-center">
          <img src={itemIcon(advice.boots)} alt={itemName(advice.boots)} title={`${itemName(advice.boots)} (T2)`} width={40} height={40} className="rounded-lg ring-1 ring-white/10" />
          <span className="mt-0.5 text-[0.55rem] font-bold uppercase text-faint">T2 boots</span>
        </span>
      )}
      {items.map((slug, i) => (
        <span key={slug} className="inline-flex items-center gap-2.5">
          <span className="relative">
            <img src={itemIcon(slug)} alt={itemName(slug)} title={`${itemName(slug)} · ${itemCost(slug)}g`} width={46} height={46} className="rounded-lg ring-1 ring-white/10" />
            <span className="absolute -left-1.5 -top-1.5 grid h-[18px] w-[18px] place-items-center rounded-full bg-[#0e1322] text-[0.6rem] font-bold text-accent ring-1 ring-line">{i + 1}</span>
          </span>
          {advice.bootsUpgrade && i + 1 === upAfter && (
            <span className="relative inline-flex flex-col items-center">
              <img src={itemIcon(advice.bootsUpgrade)} alt={itemName(advice.bootsUpgrade)} title={`Upgrade to ${itemName(advice.bootsUpgrade)} (~10:00)`} width={40} height={40} className="rounded-lg ring-1 ring-gold/40" />
              <span className="mt-0.5 text-[0.55rem] font-bold uppercase text-gold">T3 @10:00</span>
            </span>
          )}
        </span>
      ))}
    </div>
  );
}

/** The AI build advisor. Used standalone on /counter (full picker + enemy team)
 *  and inside Build Studio with `presetChampion` locked and `hideEnemies` set
 *  -- the studio "generate my build" is a personal build, not a counter build. */
export function EnemyBuildAdvisor({ presetChampion, hideEnemies }: { presetChampion?: string; hideEnemies?: boolean }) {
  const roster = useMemo(() => rosterList(), []);
  const presetRole = presetChampion ? roster.find((c) => c.name === presetChampion)?.role ?? "" : "";
  const [champ, setChamp] = useState<string | null>(presetChampion ?? null);
  const [role, setRole] = useState(presetRole);
  const [playstyle, setPlaystyle] = useState<string>("standard");
  const [objective, setObjective] = useState<string>("balanced");
  const [enemies, setEnemies] = useState<(string | null)[]>(Array(5).fill(null));
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [advice, setAdvice] = useState<Advice | null>(null);

  // the champion's home role, to flag off-role picks (Support Graves etc.)
  const naturalRole = champ ? roster.find((c) => c.name === champ)?.role ?? "" : "";
  const roleMismatch = Boolean(champ && role && naturalRole && role !== naturalRole);
  // "standard" is the best build on paper, so it ignores the enemy team.
  const enemiesIgnored = playstyle === "standard";

  const pickChamp = (name: string) => {
    setChamp(name);
    const r = roster.find((c) => c.name === name);
    if (r?.role) setRole(r.role);
  };

  const reset = () => {
    setChamp(presetChampion ?? null);
    setRole(presetRole);
    setPlaystyle("standard");
    setObjective("balanced");
    setEnemies(Array(5).fill(null));
    setAdvice(null);
  };

  // Simulated progress: the advisor gives no streaming signal, so we ease toward
  // ~92% over the expected ~30s and snap to 100% when the response lands.
  useEffect(() => {
    if (!loading) { setProgress(0); return; }
    setProgress(6);
    const started = Date.now();
    const id = setInterval(() => {
      const t = (Date.now() - started) / 30_000; // fraction of expected time
      setProgress(Math.min(92, 6 + 86 * (1 - Math.exp(-2.2 * t))));
    }, 250);
    return () => clearInterval(id);
  }, [loading]);

  async function generate() {
    if (!champ) return;
    setLoading(true);
    setAdvice(null);
    try {
      const res = await fetch("/api/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          champion: champ, role, playstyle, objective,
          // hidden in the studio, and ignored entirely for the standard build
          enemies: hideEnemies || enemiesIgnored ? [] : enemies.filter(Boolean),
        }),
      });
      setProgress(100);
      setAdvice(await res.json());
    } catch (e) {
      setAdvice({ error: String(e) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* inputs */}
      <div className="glass space-y-4 rounded-2xl p-4">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <p className="mb-1 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Your champion</p>
            {presetChampion ? (
              <span className="inline-block rounded-lg border border-line bg-white/[0.03] px-3 py-2 text-sm font-medium">{presetChampion}</span>
            ) : (
              <Picker value={champ} onPick={pickChamp} placeholder="Pick champion" />
            )}
          </div>
          <div>
            <p className="mb-1 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Playstyle</p>
            <select value={playstyle} onChange={(e) => setPlaystyle(e.target.value)}
              className="rounded-lg border border-line bg-[#0e1322] px-2 py-2 text-sm text-text outline-none">
              {PLAYSTYLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div>
            <p className="mb-1 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Optimize for</p>
            <select value={objective} onChange={(e) => setObjective(e.target.value)}
              className="rounded-lg border border-line bg-[#0e1322] px-2 py-2 text-sm text-text outline-none">
              {OBJECTIVES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div>
            <p className="mb-1 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Role</p>
            <select value={role} onChange={(e) => setRole(e.target.value)}
              className={`rounded-lg border bg-[#0e1322] px-2 py-2 text-sm outline-none ${roleMismatch ? "border-amber-500/60 text-amber-300" : "border-line text-text"}`}>
              {!role && <option value="">Any</option>}
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
        </div>
        {roleMismatch && (
          <p className="text-xs text-amber-300">
            Not recommended: {champ} is usually played {naturalRole}, not {role}. The build may be off-meta.
          </p>
        )}
        {!hideEnemies && (
          <div>
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Enemy team (up to 5)</p>
              {enemiesIgnored && (
                <span className="text-[0.65rem] text-faint">· ignored for the Standard build (best on paper)</span>
              )}
            </div>
            <div className={`flex flex-wrap gap-2 transition-opacity ${enemiesIgnored ? "opacity-40" : ""}`}>
              {enemies.map((e, i) => (
                <Picker key={i} value={e} placeholder="Enemy" size={38}
                  onPick={(name) => setEnemies((p) => p.map((x, j) => (j === i ? name : x)))} />
              ))}
            </div>
          </div>
        )}
        <div className="flex items-center gap-2">
          <button onClick={generate} disabled={!champ || loading}
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-5 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40">
            {!loading && <Sparkles />}
            {loading ? "Building…" : "Generate build"}
          </button>
          <button onClick={reset} disabled={loading}
            className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-muted transition hover:text-text disabled:opacity-40">
            Reset
          </button>
        </div>
      </div>

      {loading && (
        <div className="glass rounded-2xl p-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="text-muted">
              {hideEnemies || enemiesIgnored ? "Optimizing your build" : "Reading the enemy comp and optimizing"}…
            </span>
            <span className="font-semibold text-accent">{Math.round(progress)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
            <div className="h-full rounded-full bg-accent transition-[width] duration-300 ease-out"
              style={{ width: `${progress}%` }} />
          </div>
          <p className="mt-2 text-xs text-faint">This usually takes about 30 seconds.</p>
        </div>
      )}

      {advice && !loading && (
        advice.error ? (
          <p className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
            Could not build: {advice.error}
          </p>
        ) : (
          <div className="space-y-4">
            <div className="glass rounded-2xl p-4">
              <div className="mb-3 flex items-center gap-3">
                <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Build order{hideEnemies || enemiesIgnored ? ` · ${playstyle}` : " · vs your enemy comp"}</p>
                {typeof advice.engineScore === "number" && (
                  <span className="rounded-md bg-accent/15 px-2 py-0.5 text-[0.65rem] font-bold text-accent" title="Independent fight-engine score of this build (sanity check, not the decision).">
                    engine {advice.engineScore}
                  </span>
                )}
                {advice.validationErrors?.length ? (
                  <span className="rounded-md bg-amber-500/15 px-2 py-0.5 text-[0.65rem] font-bold text-amber-300" title={advice.validationErrors.join("; ")}>
                    needs review
                  </span>
                ) : null}
              </div>
              <ItemStrip advice={advice} />
            </div>

            {advice.runes && (
              <div className="glass rounded-2xl p-4">
                <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Runes · {advice.runes.primaryTree}</p>
                <div className="flex flex-wrap items-center gap-2">
                  {[advice.runes.keystone, ...advice.runes.minors, advice.runes.flex].map((rn, i) => (
                    <span key={rn + i} className="flex items-center gap-1.5 rounded-md bg-white/5 px-2 py-1 text-xs">
                      {runeIcon(rn) && <img src={runeIcon(rn)!} alt={rn} width={20} height={20} />}
                      {rn}{i === 0 && <span className="text-[0.6rem] font-bold text-accent"> KEY</span>}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {advice.situational?.length ? (
              <div className="glass rounded-2xl p-4">
                <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Situational swaps</p>
                <div className="space-y-1.5 text-sm">
                  {advice.situational.map((s, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <img src={itemIcon(s.item)} alt={itemName(s.item)} width={24} height={24} className="rounded" />
                      <span className="font-medium">{itemName(s.item)}</span>
                      <span className="text-muted">when {s.when}{s.replaces ? ` (over ${itemName(s.replaces)})` : ""}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {advice.why?.length ? (
              <div className="glass rounded-2xl p-4">
                <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Why this build</p>
                <ul className="space-y-1 text-sm text-muted">
                  {advice.why.map((w, i) => <li key={i}>· {w}</li>)}
                </ul>
              </div>
            ) : null}
          </div>
        )
      )}
    </div>
  );
}
