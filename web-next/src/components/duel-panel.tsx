"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { duel, mutualDuel, championTarget, dummyTarget, type DuelResult, type DuelTarget, type MutualDuelResult } from "@/lib/engine";
import { hasSimulatableKit } from "@/lib/customizer-data";
import { rosterList } from "@/lib/threat";
import engineData from "@/data/engine.json";
import buildsData from "@/data/builds.json";

/* eslint-disable @next/next/no-img-element */

const DATA = engineData as {
  items?: Record<string, { name?: string; icon?: string }>;
  formulas?: Record<string, {
    abilities?: Record<string, { name?: string; icon?: string }>;
    mechanics?: { kind?: string }[];
  }>;
};

/** Every champion's own recommended build, so the opponent is a real loadout.
 *  A full tank build on Ekko is not a matchup anyone has ever played. */
const BUILDS = buildsData as Record<string, {
  builds?: Record<string, {
    coreBuild?: { slug: string }[];
    boots?: { slug?: string } | null;
  }>;
}>;

const abilityName = (champ: string, slot: string): string =>
  DATA.formulas?.[champ]?.abilities?.[slot]?.name ?? slot;

/** Slot letters as players say them, rather than the storage keys. */
const SLOT_LABEL: Record<string, string> = { P: "Passive", "1": "Q", "2": "W", "3": "E", "4": "R" };

/**
 * The opponent's own recommended build, plus their boots.
 *
 * Falls back to no items rather than to a stand-in kit: fighting a champion who
 * has bought nothing is at least a real, explainable scenario, whereas dressing
 * Ekko as a tank invents a matchup and then reports a confident number about it.
 */
function enemyBuild(name: string): string[] {
  const variants = BUILDS[name]?.builds ?? {};
  const chosen = variants["standard"] ?? Object.values(variants)[0];
  if (!chosen) return [];
  const items = (chosen.coreBuild ?? []).map((i) => i.slug).filter(Boolean);
  const boots = chosen.boots?.slug;
  return boots ? [...items, boots] : items;
}

/** Why the fight is unavailable for a champion, in the player's terms. */
function lockReason(name: string): string | null {
  if (!hasSimulatableKit(name)) {
    return `${name} is not in the game yet, so there are no real ability numbers to fight with.`;
  }
  const transforms = (DATA.formulas?.[name]?.mechanics ?? []).some((m) => m.kind === "transform");
  if (transforms) {
    return `${name} changes form mid-fight and only the base form is modelled, so a result `
      + `here would quietly ignore half the kit. Switched off until the transformed state `
      + `is simulated too.`;
  }
  return null;
}

type Phase = "idle" | "fighting" | "done";
type Mode = "champion" | "dummy";
/** Who opens the fight. The engager's rotation starts this much earlier. */
type Engage = "same" | "you" | "them";
const ENGAGE_HEAD_START = 0.5;

export function DuelPanel({ name, itemSlugs, runeNames, level, scaled = false }: {
  name: string;
  itemSlugs: string[];
  runeNames: string[];
  level: number;
  /** Mirrors the stat panel's Guaranteed / Fully scaled switch. */
  scaled?: boolean;
}) {
  const [mode, setMode] = useState<Mode>("champion");
  const [enemy, setEnemy] = useState("Garen");
  const [dummyHp, setDummyHp] = useState(4000);
  const [engage, setEngage] = useState<Engage>("same");
  const [phase, setPhase] = useState<Phase>("idle");
  const [shown, setShown] = useState<DuelResult | null>(null);
  const [shownMutual, setShownMutual] = useState<MutualDuelResult | null>(null);
  const timers = useRef<number[]>([]);

  const roster = useMemo(() => rosterList(), []);
  const iconOf = useMemo(
    () => Object.fromEntries(roster.map((c) => [c.name, c.icon])) as Record<string, string>,
    [roster]);

  const target: DuelTarget | null = useMemo(
    () => (mode === "dummy"
      ? dummyTarget(dummyHp)
      : championTarget(enemy, level, enemyBuild(enemy)) ?? dummyTarget(dummyHp)),
    [mode, dummyHp, enemy, level]);

  const result = useMemo(() => {
    if (!target || !itemSlugs.length) return null;
    return duel(name, itemSlugs, runeNames, target, level, 20, scaled);
  }, [name, itemSlugs, runeNames, target, level, scaled]);

  // The enemy fights back only when their kit is actually simulatable. A
  // form-swapper or an unreleased champion would "fight back" with zero
  // damage, and an uncontested win against a silent opponent is a lie with
  // extra steps, so those matchups stay one-sided and say why.
  const enemyLocked = mode === "champion" ? lockReason(enemy) : null;
  const mutual = useMemo(() => {
    if (mode !== "champion" || enemyLocked || !itemSlugs.length) return null;
    const head = engage === "you" ? ENGAGE_HEAD_START : engage === "them" ? -ENGAGE_HEAD_START : 0;
    return mutualDuel(name, itemSlugs, runeNames, enemy, enemyBuild(enemy), [],
                      level, 20, scaled, head);
  }, [mode, enemyLocked, name, itemSlugs, runeNames, enemy, level, scaled, engage]);

  // Any change to the build, level, scaling or opponent invalidates the last
  // fight, so the numbers on screen always belong to the setup above them.
  // Tracked as derived state rather than an effect: setting state inside an
  // effect just to follow a prop causes a second render pass for something the
  // current render already knows.
  const setupKey = [name, mode, enemy, dummyHp, level, scaled, engage,
                    itemSlugs.join(","), runeNames.join(",")].join("|");
  const [lastSetup, setLastSetup] = useState(setupKey);
  if (lastSetup !== setupKey) {
    setLastSetup(setupKey);
    setPhase("idle");
    setShown(null);
    setShownMutual(null);
  }

  // A pending fight belongs to the setup that started it. Rather than cancel
  // timers when the setup changes -- which would mean touching a ref during
  // render -- the callback checks whether its own setup is still the current
  // one and drops itself if not.
  const currentSetup = useRef(setupKey);
  useEffect(() => { currentSetup.current = setupKey; }, [setupKey]);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const locked = lockReason(name);

  function fight() {
    if (!result || phase === "fighting") return;
    setPhase("fighting");
    setShown(null);
    const startedWith = setupKey;
    // The maths is instant. The pause is for the player: a number that appears
    // the very instant you click reads as a lookup rather than a fight.
    timers.current.push(window.setTimeout(() => {
      if (currentSetup.current !== startedWith) return;
      setShown(result);
      setShownMutual(mutual);
      setPhase("done");
    }, 1100));
  }

  if (locked) {
    return (
      <div className="glass mt-4 rounded-2xl p-4">
        <Heading />
        <div className="mt-3 flex items-start gap-3 rounded-xl border border-line bg-white/[0.02] p-3">
          <LockGlyph />
          <div>
            <p className="text-sm font-semibold text-text">Locked for {name}</p>
            <p className="mt-1 text-sm leading-relaxed text-muted">{locked}</p>
          </div>
        </div>
      </div>
    );
  }

  // Collapsible, open by default. The enemy picker, the HP slider and Fight all
  // live in the body rather than the summary: a control inside <summary> folds
  // the panel on every click.
  return (
    <details open className="glass group mt-4 overflow-hidden rounded-2xl">
      <summary className="flex cursor-pointer list-none items-center gap-3 p-4 pb-0">
        <span className="min-w-0 flex-1"><Heading /></span>
        <span aria-hidden className="shrink-0 text-accent transition group-open:rotate-180">⌄</span>
      </summary>
      <div className="p-4">

        <div className="mt-4 grid grid-cols-[1fr_auto_1fr] items-center gap-3">
          <Fighter name={name} icon={iconOf[name]} level={level} mine />
          <VersusMark active={phase === "fighting"} />
          {mode === "dummy" ? (
            <DummyFighter hp={target?.hp ?? dummyHp} />
          ) : (
            <Fighter name={enemy} icon={iconOf[enemy]} level={level}
                     hp={target?.hp} armor={target?.armor} mr={target?.mr} />
          )}
        </div>

        <div className="mt-3 flex justify-center gap-1.5">
          <ModeToggle active={mode === "champion"} onClick={() => setMode("champion")}>
            A champion
          </ModeToggle>
          <ModeToggle active={mode === "dummy"} onClick={() => setMode("dummy")}>
            Practice dummy
          </ModeToggle>
        </div>

        {mode === "champion" ? (
          <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
            <label htmlFor="duel-enemy" className="text-xs uppercase tracking-wide text-faint">
              Opponent
            </label>
            <select
              id="duel-enemy" value={enemy} onChange={(e) => setEnemy(e.target.value)}
              className="rounded-lg border border-line bg-[#0e1322] px-3 py-1.5 text-sm text-text"
            >
              {roster.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
            <span className="text-xs text-faint">on their recommended build</span>
            {!enemyLocked && (
              <div className="flex w-full flex-wrap items-center justify-center gap-1.5 pt-1">
                <span className="text-xs uppercase tracking-wide text-faint">Who engages</span>
                <ModeToggle active={engage === "you"} onClick={() => setEngage("you")}>You first</ModeToggle>
                <ModeToggle active={engage === "same"} onClick={() => setEngage("same")}>Same time</ModeToggle>
                <ModeToggle active={engage === "them"} onClick={() => setEngage("them")}>They first</ModeToggle>
              </div>
            )}
          </div>
        ) : (
          <div className="mt-3 flex items-center gap-3">
            <label htmlFor="dummy-hp" className="shrink-0 text-xs uppercase tracking-wide text-faint">
              Dummy health
            </label>
            <input
              id="dummy-hp" type="range" min={1000} max={10000} step={250}
              value={dummyHp} onChange={(e) => setDummyHp(Number(e.target.value))}
              className="h-1.5 flex-1 cursor-pointer accent-[var(--color-accent)]"
            />
            <span className="w-16 shrink-0 text-right text-sm font-bold tabular-nums text-accent">
              {dummyHp.toLocaleString()}
            </span>
          </div>
        )}

        <div className="mt-4 flex justify-center">
          <button
            onClick={fight}
            disabled={!result || phase === "fighting"}
            data-tour="lab-fight"
            className={`rounded-xl px-8 py-3 text-sm font-bold uppercase tracking-wide transition ${
              !result ? "cursor-not-allowed border border-line text-faint"
                : phase === "fighting" ? "bg-accent/40 text-black"
                : "bg-accent text-black hover:brightness-110 active:scale-[0.98]"}`}
          >
            {!result ? "Add an item first"
              : phase === "fighting" ? "Fighting…"
              : phase === "done" ? "Fight again" : "Fight"}
          </button>
        </div>
      </div>

      {phase !== "idle" && (
        <div className="border-t border-line/60 bg-black/20 p-4">
          {phase === "fighting" ? <FightingBar /> : shown && (
            <Results result={shown} attacker={name}
                     enemy={mode === "dummy" ? "The dummy" : enemy}
                     dummy={mode === "dummy"} scaled={scaled}
                     mutual={shownMutual} enemyLocked={enemyLocked} />
          )}
        </div>
      )}
    </details>
  );
}

function Heading() {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Test this build</p>
      <span className="text-[0.65rem] text-faint">damage check</span>
    </div>
  );
}

function LockGlyph() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.8" className="mt-0.5 shrink-0 text-faint" aria-hidden>
      <rect x="4" y="10" width="16" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

function Fighter({ name, icon, level, hp, armor, mr, mine = false }: {
  name: string; icon?: string; level: number;
  hp?: number; armor?: number; mr?: number; mine?: boolean;
}) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className={`relative rounded-full p-[2px] ${
        mine ? "bg-gradient-to-br from-accent to-accent/25"
             : "bg-gradient-to-br from-bad to-bad/25"}`}>
        {icon ? (
          <img src={icon} alt="" width={56} height={56}
               className="h-14 w-14 rounded-full object-cover" loading="lazy" />
        ) : (
          <span className="grid h-14 w-14 place-items-center rounded-full bg-surface text-lg font-bold">
            {name.slice(0, 1)}
          </span>
        )}
        <span className="absolute -bottom-1 left-1/2 -translate-x-1/2 rounded-full bg-[#0e1322] px-1.5 text-[0.6rem] font-bold text-muted">
          {level}
        </span>
      </div>
      <p className="max-w-[7rem] truncate text-center text-sm font-semibold">{name}</p>
      {hp != null ? (
        <p className="text-center text-[0.65rem] tabular-nums text-faint">
          {hp.toLocaleString()} hp · {armor} ar · {mr} mr
        </p>
      ) : (
        <p className="text-[0.65rem] uppercase tracking-wide text-accent">your build</p>
      )}
    </div>
  );
}

function ModeToggle({ active, onClick, children }: {
  active: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-lg border px-3 py-1 text-xs font-semibold transition ${
        active ? "border-accent/60 bg-accent/15 text-accent"
               : "border-line text-muted hover:border-accent/40 hover:text-text"}`}
    >
      {children}
    </button>
  );
}

/** No portrait and no resistances: the point of the dummy is a clean read of
 *  raw output, with nothing in the way. */
function DummyFighter({ hp }: { hp: number }) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="rounded-full bg-gradient-to-br from-muted to-muted/25 p-[2px]">
        <span className="grid h-14 w-14 place-items-center rounded-full bg-surface">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="1.6" className="text-muted" aria-hidden>
            <circle cx="12" cy="12" r="9" />
            <circle cx="12" cy="12" r="5" />
            <circle cx="12" cy="12" r="1.4" fill="currentColor" />
          </svg>
        </span>
      </div>
      <p className="text-sm font-semibold">Practice dummy</p>
      <p className="text-[0.65rem] tabular-nums text-faint">
        {hp.toLocaleString()} hp · no resistances
      </p>
    </div>
  );
}

function VersusMark({ active }: { active: boolean }) {
  return (
    <span className={`text-2xl font-black italic tracking-tighter text-faint ${
      active ? "motion-safe:animate-pulse" : ""}`}>
      VS
    </span>
  );
}

function FightingBar() {
  return (
    <div>
      <p className="mb-2 text-center text-xs font-semibold uppercase tracking-wide text-accent">
        Trading blows…
      </p>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div className="h-full w-1/3 rounded-full bg-accent motion-safe:animate-[sheen_1.1s_ease-in-out_infinite]" />
      </div>
    </div>
  );
}

function Results({ result, attacker, enemy, scaled, dummy = false, mutual = null, enemyLocked = null }: {
  result: DuelResult; attacker: string; enemy: string; scaled: boolean; dummy?: boolean;
  mutual?: MutualDuelResult | null; enemyLocked?: string | null;
}) {
  const killed = result.ttk !== null;
  const casts = result.casts.reduce((n, c) => n + c.casts, 0);
  return (
    <div className="motion-safe:animate-[fadeUp_.35s_ease-out]">
      {mutual ? (
        <Verdict mutual={mutual} you={attacker} them={enemy} />
      ) : (
        <>
          <p className={`text-center text-lg font-black tracking-tight ${
            killed ? "text-accent" : "text-bad"}`}>
            {killed ? `${enemy} down in ${result.ttk}s` : `${enemy} survives`}
          </p>
          <p className="mt-0.5 text-center text-xs text-faint">
            {killed
              ? `${result.autos} attacks and ${casts} abilities`
              : `not enough damage inside 20 seconds`}
            {scaled ? " · fully scaled" : ""}
          </p>
        </>
      )}

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Time to kill" value={killed ? `${result.ttk}s` : "—"} accent={killed} />
        <Stat label="Damage per second" value={result.dps.toLocaleString()} />
        <Stat label="Attacks landed" value={`${result.autos} of ${result.autosIdeal}`} />
        <Stat label="Overkill" value={result.overkill.toLocaleString()} />
      </div>

      {result.combo.length > 0 && (
        <div className="mt-3">
          <p className="mb-1.5 text-[0.6rem] font-bold uppercase tracking-wide text-faint">
            The combo
          </p>
          <div className="flex flex-wrap items-center gap-1">
            {result.combo.map((step, i) => (
              <span key={i}
                    className="flex items-center gap-1 motion-safe:animate-[fadeUp_.3s_ease-out_both]"
                    style={{ animationDelay: `${i * 45}ms` }}>
                {i > 0 && <span className="text-faint">›</span>}
                <span className={`rounded-md px-2 py-0.5 text-xs font-bold ${
                  step === "auto" ? "bg-white/[0.06] text-muted" : "bg-accent/15 text-accent"}`}>
                  {step === "auto" ? "attack" : SLOT_LABEL[step] ?? step}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-3">
        <p className="mb-1.5 text-[0.6rem] font-bold uppercase tracking-wide text-faint">
          Abilities used over the fight
        </p>
        <div className="flex flex-wrap gap-1.5">
          {result.casts.length === 0 && <span className="text-sm text-muted">Attacks only.</span>}
          {result.casts.map((c) => (
            <span key={c.slot}
                  className="rounded-lg border border-line bg-white/[0.04] px-2.5 py-1 text-xs">
              <span className="font-bold text-accent">{SLOT_LABEL[c.slot] ?? c.slot}</span>{" "}
              {abilityName(attacker, c.slot)}
              <span className="ml-1.5 font-bold tabular-nums text-muted">&times;{c.casts}</span>
            </span>
          ))}
        </div>
      </div>

      <DamageSplit split={result.byType} total={result.damage} />

      {mutual && (
        <div className="mt-3 rounded-xl border border-bad/25 bg-bad/[0.05] p-3">
          <p className="mb-1.5 text-[0.6rem] font-bold uppercase tracking-wide text-bad/90">
            {enemy} fights back
          </p>
          <p className="text-xs leading-relaxed text-muted">
            {mutual.them.ttk != null
              ? <>Their combo kills you in <span className="font-bold text-text">{mutual.them.ttk}s</span> at {mutual.them.dps.toLocaleString()} damage per second.</>
              : <>Their combo cannot kill you inside 20 seconds ({mutual.them.dps.toLocaleString()} damage per second).</>}
          </p>
          {mutual.them.combo.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-1">
              {mutual.them.combo.map((step, i) => (
                <span key={i} className="flex items-center gap-1">
                  {i > 0 && <span className="text-faint">›</span>}
                  <span className={`rounded-md px-2 py-0.5 text-xs font-bold ${
                    step === "auto" ? "bg-white/[0.06] text-muted" : "bg-bad/15 text-bad"}`}>
                    {step === "auto" ? "attack" : SLOT_LABEL[step] ?? step}
                  </span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      <p className="mt-3 border-t border-line/60 pt-2.5 text-[0.7rem] leading-relaxed text-faint">
        {dummy
          ? "A bare target with no armor or magic resist, so this is the build's raw output."
          : mutual
            ? `Both champions stand still and run their full rotation. Nobody dodges, heals, repositions or holds a cooldown.`
            : enemyLocked
              ? `${enemy} cannot fight back here: ${enemyLocked}`
              : `${enemy} stands still on their recommended build and does not dodge, heal or fight back.`}
        {" "}A damage check, not a prediction of a real fight.
      </p>
    </div>
  );
}

/** The headline of a two-sided fight, in the model's own terms. */
function Verdict({ mutual, you, them }: { mutual: MutualDuelResult; you: string; them: string }) {
  const { verdict, margin, survivorHp } = mutual;
  const hpPct = survivorHp != null ? Math.round(survivorHp * 100) : null;
  if (verdict === "you") {
    return (
      <>
        <p className="text-center text-lg font-black tracking-tight text-accent">
          {them} dies first · {mutual.you.ttk}s
        </p>
        <p className="mt-0.5 text-center text-xs text-faint">
          {mutual.them.ttk != null
            ? `their kill needed ${mutual.them.ttk}s, ${margin}s too slow`
            : "their combo never gets there"}
          {hpPct != null ? ` · you walk away at ${hpPct}% health` : ""}
        </p>
      </>
    );
  }
  if (verdict === "them") {
    return (
      <>
        <p className="text-center text-lg font-black tracking-tight text-bad">
          {you} dies first · {mutual.them.ttk}s
        </p>
        <p className="mt-0.5 text-center text-xs text-faint">
          {mutual.you.ttk != null
            ? `your kill needed ${mutual.you.ttk}s, ${margin}s too slow`
            : "your combo never gets there"}
          {hpPct != null ? ` · they walk away at ${hpPct}% health` : ""}
        </p>
      </>
    );
  }
  if (verdict === "trade") {
    return (
      <>
        <p className="text-center text-lg font-black tracking-tight text-gold">
          Double kill · both inside {Math.max(mutual.you.ttk ?? 0, mutual.them.ttk ?? 0)}s
        </p>
        <p className="mt-0.5 text-center text-xs text-faint">
          the two kill clocks land within a quarter second, so whoever actually engages first wins this one
        </p>
      </>
    );
  }
  return (
    <>
      <p className="text-center text-lg font-black tracking-tight text-muted">
        Nobody dies
      </p>
      <p className="mt-0.5 text-center text-xs text-faint">
        neither combo reaches a kill inside 20 seconds
      </p>
    </>
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
