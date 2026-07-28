"use client";

import { useMemo, useState } from "react";
import { duel, championTarget, dummyTarget, type DuelTarget } from "@/lib/engine";
import { hasSimulatableKit } from "@/lib/customizer-data";
import { rosterList } from "@/lib/threat";
import engineData from "@/data/engine.json";

const DATA = engineData as {
  items?: Record<string, { name?: string; icon?: string }>;
  formulas?: Record<string, { abilities?: Record<string, { name?: string }> }>;
};
const abilityName = (champ: string, slot: string): string =>
  DATA.formulas?.[champ]?.abilities?.[slot]?.name ?? slot;

/** Slot letters as players say them, rather than the storage keys. */
const SLOT_LABEL: Record<string, string> = { P: "Passive", "1": "Q", "2": "W", "3": "E", "4": "R" };

/** A stand-in defensive build, so "vs a tank" means something without asking
 *  the player to assemble one. Slugs are checked against the item data below. */
const TANK_BUILD = ["sunfire-aegis", "dead-mans-plate", "thornmail",
                    "force-of-nature", "warmogs-armor"];
const SQUISHY_BUILD = ["rabadons-deathcap", "void-staff"];

type Mode = "dummy" | "champion";

export function DuelPanel({ name, itemSlugs, runeNames, level }: {
  name: string;
  itemSlugs: string[];
  runeNames: string[];
  level: number;
}) {
  const [mode, setMode] = useState<Mode>("champion");
  const [enemy, setEnemy] = useState("Garen");
  const [enemyKit, setEnemyKit] = useState<"tank" | "squishy" | "naked">("tank");
  const [dummyHp, setDummyHp] = useState(4000);

  const roster = useMemo(
    () => rosterList().map((c) => c.name).sort((a, b) => a.localeCompare(b)), []);

  const target: DuelTarget | null = useMemo(() => {
    if (mode === "dummy") return dummyTarget(dummyHp);
    const build = enemyKit === "tank" ? TANK_BUILD
      : enemyKit === "squishy" ? SQUISHY_BUILD : [];
    return championTarget(enemy, level, build);
  }, [mode, dummyHp, enemy, enemyKit, level]);

  const result = useMemo(() => {
    if (!target || !itemSlugs.length) return null;
    return duel(name, itemSlugs, runeNames, target, level);
  }, [name, itemSlugs, runeNames, target, level]);

  // A champion whose abilities carry no numbers would produce a confident zero,
  // which is worse than saying nothing.
  if (!hasSimulatableKit(name)) {
    return (
      <div className="glass mt-4 rounded-2xl p-4">
        <PanelHeading />
        <p className="mt-2 text-sm text-muted">
          {name}&rsquo;s abilities are not modelled in enough detail to simulate yet, so this
          would report numbers we cannot stand behind. The stats and item effects above are
          unaffected.
        </p>
      </div>
    );
  }

  return (
    <div className="glass mt-4 rounded-2xl p-4">
      <PanelHeading />

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Toggle active={mode === "champion"} onClick={() => setMode("champion")}>
          Against a champion
        </Toggle>
        <Toggle active={mode === "dummy"} onClick={() => setMode("dummy")}>
          Against a dummy
        </Toggle>
      </div>

      {mode === "champion" ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <select
            value={enemy}
            onChange={(e) => setEnemy(e.target.value)}
            aria-label="Enemy champion"
            className="rounded-lg border border-line bg-[#0e1322] px-3 py-2 text-sm text-text"
          >
            {roster.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <div className="flex gap-1.5">
            {(["tank", "squishy", "naked"] as const).map((k) => (
              <Toggle key={k} active={enemyKit === k} onClick={() => setEnemyKit(k)} small>
                {k === "tank" ? "Full tank build" : k === "squishy" ? "Glass cannon" : "No items"}
              </Toggle>
            ))}
          </div>
        </div>
      ) : (
        <div className="mt-3 flex items-center gap-3">
          <label htmlFor="dummy-hp" className="text-xs uppercase tracking-wide text-faint">
            Dummy health
          </label>
          <input
            id="dummy-hp" type="range" min={1000} max={10000} step={250}
            value={dummyHp} onChange={(e) => setDummyHp(Number(e.target.value))}
            className="h-1.5 flex-1 cursor-pointer accent-[var(--color-accent)]"
          />
          <span className="w-14 text-right text-sm font-bold tabular-nums text-accent">
            {dummyHp.toLocaleString()}
          </span>
        </div>
      )}

      {!itemSlugs.length ? (
        <p className="mt-4 text-sm text-muted">Add an item to run the fight.</p>
      ) : !result || !target ? (
        <p className="mt-4 text-sm text-muted">This matchup cannot be simulated.</p>
      ) : (
        <>
          <p className="mt-3 text-xs text-faint">
            {target.label} at level {level}: {target.hp.toLocaleString()} health,{" "}
            {target.armor} armor, {target.mr} magic resist
          </p>

          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Time to kill" value={result.ttk === null ? "—" : `${result.ttk}s`}
                  accent={result.ttk !== null} />
            <Stat label="Damage per second" value={result.dps.toLocaleString()} />
            <Stat label="Attacks landed" value={`${result.autos} of ${result.autosIdeal}`} />
            <Stat label="Overkill" value={result.overkill.toLocaleString()} />
          </div>

          {result.ttk === null && (
            <p className="mt-2 rounded-lg bg-bad/10 px-2.5 py-1.5 text-xs font-medium text-bad">
              This build does not kill {target.label} inside 20 seconds.
            </p>
          )}

          <div className="mt-3">
            <p className="mb-1.5 text-[0.6rem] font-bold uppercase tracking-wide text-faint">
              Abilities used
            </p>
            <div className="flex flex-wrap gap-1.5">
              {result.casts.length === 0 && (
                <span className="text-sm text-muted">Attacks only.</span>
              )}
              {result.casts.map((c) => (
                <span key={c.slot}
                      className="rounded-lg border border-line bg-white/[0.04] px-2.5 py-1 text-xs">
                  <span className="font-bold text-accent">{SLOT_LABEL[c.slot] ?? c.slot}</span>{" "}
                  {abilityName(name, c.slot)}
                  <span className="ml-1.5 font-bold tabular-nums text-muted">&times;{c.casts}</span>
                </span>
              ))}
            </div>
          </div>

          <DamageSplit split={result.byType} total={result.damage} />

          <p className="mt-3 border-t border-line/60 pt-2.5 text-[0.7rem] leading-relaxed text-faint">
            A practice-tool dummy with {target.label}&rsquo;s defences. It does not move, dodge,
            heal, build back or fight you, so treat this as a damage check rather than a
            prediction of a real fight.
          </p>
        </>
      )}
    </div>
  );
}

function PanelHeading() {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">
        Test this build
      </p>
      <span className="text-[0.65rem] text-faint">damage check</span>
    </div>
  );
}

function Toggle({ active, onClick, children, small = false }: {
  active: boolean; onClick: () => void; children: React.ReactNode; small?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-lg border px-3 ${small ? "py-1 text-xs" : "py-1.5 text-sm"} font-semibold transition ${
        active ? "border-accent/60 bg-accent/15 text-accent"
               : "border-line text-muted hover:border-accent/40 hover:text-text"}`}
    >
      {children}
    </button>
  );
}

function Stat({ label, value, accent = false }: {
  label: string; value: string; accent?: boolean;
}) {
  return (
    <div className="rounded-xl border border-line bg-white/[0.03] px-3 py-2">
      <p className="text-[0.6rem] uppercase tracking-wide text-faint">{label}</p>
      <p className={`text-lg font-bold tabular-nums ${accent ? "text-accent" : "text-text"}`}>
        {value}
      </p>
    </div>
  );
}

function DamageSplit({ split, total }: {
  split: { physical: number; magic: number; true: number }; total: number;
}) {
  const rows = [
    { key: "physical", label: "Physical", value: split.physical, cls: "bg-[#ff9d5c]" },
    { key: "magic", label: "Magic", value: split.magic, cls: "bg-[#5cc8ff]" },
    { key: "true", label: "True", value: split.true, cls: "bg-[#e6e6e6]" },
  ].filter((r) => r.value > 0);
  if (!rows.length || total <= 0) return null;

  return (
    <div className="mt-3">
      <p className="mb-1.5 text-[0.6rem] font-bold uppercase tracking-wide text-faint">
        Damage dealt
      </p>
      <div className="flex h-2 overflow-hidden rounded-full bg-white/[0.06]">
        {rows.map((r) => (
          <div key={r.key} className={r.cls}
               style={{ width: `${Math.max(1, (r.value / total) * 100)}%` }} />
        ))}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
        {rows.map((r) => (
          <span key={r.key} className="flex items-center gap-1.5">
            <span className={`h-2 w-2 rounded-full ${r.cls}`} />
            {r.label}
            <span className="font-bold tabular-nums text-text">{r.value.toLocaleString()}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
