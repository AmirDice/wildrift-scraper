"use client";

import { useEffect, useMemo, useState } from "react";
import { rosterList, type RosterChampion } from "@/lib/threat";
import engineData from "@/data/engine.json";
import playstyleData from "@/data/playstyles.json";
import { DAMAGE_PATHS, GAME_PHASES, HYBRID_DAMAGE_CHAMPIONS, KAYN_FORMS } from "@/lib/build-options";
import { useAccount, type QuotaState } from "@/components/account-provider";
import { GoogleSignInButton } from "@/components/google-sign-in";
import { BuildFeedback } from "@/components/build-feedback";
import { ShareBuildButton } from "@/components/share-build";
import { AddToAlbumButton } from "@/components/add-to-album";
import { LockPicker } from "@/components/lock-picker";

/* eslint-disable @next/next/no-img-element */

// item/boot icons were rehosted to /items/<slug>.webp; runes carry their own.
const DATA = engineData as {
  items?: Record<string, { name?: string; cost?: number; icon?: string }>;
  runes?: Record<string, { icon?: string }>;
};
const itemName = (slug: string): string => DATA.items?.[slug]?.name ?? slug;
const itemCost = (slug: string): number => DATA.items?.[slug]?.cost ?? 0;
// use the STORED icon, not `/items/<slug>.webp`: aliased items (Lord Dominik's
// Regard) keep the source file name (dominiks-regards.webp), so constructing
// the path from the canonical slug 404s.
const itemIcon = (slug: string): string => DATA.items?.[slug]?.icon ?? `/items/${slug}.webp`;
const runeIcon = (name: string): string | null => DATA.runes?.[name]?.icon ?? null;

/**
 * "Why this build" for a GENERATED build.
 *
 * The old version listed only the free-text `why` bullets. This adds the
 * per-element reasoning the advisor now returns -- item reasons from
 * candidateItemScores, rune reasons from runeReasons, and the boots reason --
 * each shown with its own icon and name, so the reader can see WHICH piece each
 * line is about rather than reading a wall of prose. Counter mode returns none
 * of this (skipped for speed), so
 * the whole block simply renders nothing then.
 */
function WhyRow({ icon, round, name, reason }: {
  icon?: string | null; round?: boolean; name: string; reason: string;
}) {
  return (
    <li className="flex items-start gap-2.5">
      {icon ? (
        <img src={icon} alt="" width={26} height={26}
          className={`mt-0.5 shrink-0 ring-1 ring-white/10 ${round ? "rounded-full" : "rounded-md"}`} loading="lazy" />
      ) : (
        <span className="mt-0.5 h-[26px] w-[26px] shrink-0 rounded-md bg-white/[0.06]" />
      )}
      <span className="min-w-0 text-sm text-muted">
        <span className="font-semibold text-text">{name}</span>
        {reason ? <> — {reason}</> : null}
      </span>
    </li>
  );
}

function WhyThisBuild({ advice }: { advice: Advice }) {
  const reasonBySlug = new Map(
    (advice.candidateItemScores ?? []).map((row) => [row.item, row.reason]),
  );
  const itemRows = (advice.items ?? [])
    .map((slug) => ({ icon: itemIcon(slug), name: itemName(slug), reason: reasonBySlug.get(slug) ?? "" }))
    .filter((row) => row.reason);

  const bootSlug = advice.bootsUpgrade ?? advice.boots;
  const bootRow = bootSlug && advice.bootsReason
    ? { icon: itemIcon(bootSlug), name: itemName(bootSlug), reason: advice.bootsReason }
    : null;

  const rr = advice.runeReasons;
  const runeRows = advice.runes && rr
    ? [
        { name: advice.runes.keystone, reason: rr.keystone },
        ...advice.runes.minors.map((m, i) => ({ name: m, reason: rr.minors?.[i] })),
        { name: advice.runes.flex, reason: rr.flex },
      ].filter((row): row is { name: string; reason: string } => Boolean(row.name && row.reason))
    : [];

  const hasDetail = itemRows.length > 0 || bootRow || runeRows.length > 0;
  if (!hasDetail) return null;

  return (
    <div className="glass rounded-2xl p-4">
      <p className="mb-3 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Why this is the optimal build</p>
      {itemRows.length > 0 && (
        <div className="mb-3">
          <p className="mb-1.5 text-[0.6rem] font-bold uppercase tracking-wide text-faint">Items</p>
          <ul className="space-y-1.5">
            {itemRows.map((row, i) => <WhyRow key={`i${i}`} {...row} />)}
          </ul>
        </div>
      )}
      {bootRow && (
        <div className="mb-3">
          <p className="mb-1.5 text-[0.6rem] font-bold uppercase tracking-wide text-faint">Boots</p>
          <ul className="space-y-1.5"><WhyRow {...bootRow} /></ul>
        </div>
      )}
      {runeRows.length > 0 && (
        <div>
          <p className="mb-1.5 text-[0.6rem] font-bold uppercase tracking-wide text-faint">Runes</p>
          <ul className="space-y-1.5">
            {runeRows.map((row, i) => (
              <WhyRow key={`r${i}`} icon={runeIcon(row.name)} round name={row.name} reason={row.reason} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

type AdvisorMode = "studio" | "counter";
type PlaystyleDefinition = { key: string; label: string; description: string; prompt: string };

const PLAYSTYLES = playstyleData.definitions as PlaystyleDefinition[];
const PLAYSTYLES_BY_CLASS = playstyleData.byClass as Record<string, string[]>;
const PLAYSTYLE_OVERRIDES = playstyleData.overrides as Record<string, string[]>;
/** Ranged-class champions who actually attack in melee. See _meleeNote. */
const MELEE_IN_RANGED_CLASS = new Set(playstyleData.meleeInRangedClass as string[]);

function playstylesFor(champion: RosterChampion | undefined, mode: AdvisorMode): PlaystyleDefinition[] {
  const allowed = champion
    ? [...(PLAYSTYLE_OVERRIDES[champion.name] ?? PLAYSTYLES_BY_CLASS[champion.class] ?? ["standard", "damage"])]
    : ["standard"];
  // Poke comes from the class list, and three classes that grant it (Mage,
  // Enchanter, Marksman) each contain melee champions. Poke means repeatable
  // pressure from range, so offering it to Lillia or Nilah advertises a build
  // they cannot execute.
  if (champion && MELEE_IN_RANGED_CLASS.has(champion.name)) {
    const poke = allowed.indexOf("poke");
    if (poke !== -1) allowed.splice(poke, 1);
  }
  if (champion?.role === "Support" && !allowed.includes("utility")) allowed.push("utility");
  const modeKeys = mode === "counter"
    ? ["adaptive", ...allowed.filter((key) => key !== "standard")]
    : allowed;
  return modeKeys
    .map((key) => PLAYSTYLES.find((style) => style.key === key))
    .filter((style): style is PlaystyleDefinition => Boolean(style));
}

// Orthogonal optimization axis, sent alongside the playstyle.
const OBJECTIVES = [
  ["balanced", "Balanced"], ["maxstats", "Max stats"], ["maxsynergy", "Max synergy"],
] as const;

const OBJECTIVE_HELP: Record<string, string> = {
  balanced: "Balance practical win rate, synergy, timing, damage, and survivability.",
  maxstats: "Prefer efficient raw stats that the champion can use well.",
  maxsynergy: "Prefer interactions between the champion kit, items, and runes.",
};

const ROLES = ["Baron", "Jungle", "Mid", "Dragon", "Support"] as const;

/** Measured generation time, mid-range: real runs land between 46s and 66s.
 *  Both the progress curve and the note under the bar read from this, so they
 *  can never drift apart again. */
const EXPECTED_MS = 55_000;

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

export type Advice = {
  items?: string[];
  boots?: string;
  bootsUpgrade?: string;
  situationalBoots?: { boots: string; bootsUpgrade?: string; when: string }[];
  runes?: { keystone: string; primaryTree: string; minors: string[]; flex: string };
  /** One-line reasons for the boots and each rune, so "Why this build" can
   *  explain more than the items. Absent in counter mode (skipped for speed). */
  bootsReason?: string;
  runeReasons?: { keystone?: string; minors?: string[]; flex?: string };
  /** Two summoner spells, each with a DDragon icon. */
  summoners?: { name: string; icon: string }[];
  /** `atPosition` is the purchase slot the swap goes in at, 1-5.
   *
   *  A swap is a REORDERING, not a one-for-one trade: the advisor may insert an
   *  item early and push the rest back, so `resultingOrder` carries the whole
   *  five-item build the swap produces. `replaces`/`atPosition` remain populated
   *  as aliases of `removedItem`/`insertAtPosition` for existing renderers. */
  situational?: {
    item: string;
    when: string;
    replaces: string;
    atPosition?: number;
    removedItem?: string;
    insertAtPosition?: number;
    resultingOrder?: string[];
  }[];
  /** A rune that answers a matchup, replacing either another rune or an item.
   *  When it replaces an ITEM it frees a build slot, so `freedSlotItem` and
   *  `resultingItems` say what fills it -- otherwise the advice is a four-item
   *  build. */
  situationalRunes?: {
    rune: string;
    replaces: string;
    replacesType: "rune" | "item";
    replacesLabel?: string;
    freedSlotItem?: string;
    atPosition?: number;
    resultingItems?: string[];
    when: string;
  }[];
  snowballSwap?: {
    item: string;
    when: string;
    replaces: string;
    atPosition?: number;
    resultingOrder?: string[];
  } | null;
  /** Competitive comparison set, separate from the mandatory audit so the audit
   *  does not consume the candidate budget. */
  candidateItemScores?: { item: string; score: number; reason: string }[];
  mandatoryAuditScores?: { item: string; score: number; reason: string }[];
  /** Legal-but-wasteful overlaps and thin inputs. Not failures. */
  validationWarnings?: string[];
  why?: string[];
  buildScore?: {
    overall: number;
    burst: number;
    sustainedDamage: number;
    survivability: number;
    mobility: number;
    utility: number;
    earlyPower: number;
    confidence: number;
    reason: string;
  };
  validationErrors?: string[];
  /** Additive metadata (schemaVersion 2): what the build was optimised for, and
   *  the compact counter summary in counter mode. Old responses omit them. */
  schemaVersion?: number;
  requestMeta?: {
    mode: string;
    requestedPlaystyle: string;
    resolvedPlaystyle: string;
    playstyleAdjustment: string | null;
    powerCurve: string;
    optimizationGoal: string;
    riskTolerance: string;
    enemyContext: string;
  };
  counterSummary?: {
    confidence: number;
    counterPriorities: string[];
    threatResponses: { choiceType: string; choice: string; answers: string[]; reason: string }[];
    acceptedTradeoffs: string[];
    unansweredThreats: string[];
    allyContextUsed: boolean;
  };
  error?: string;
  /** Echoed back by /api/build so the UI can show the day's remaining budget. */
  quota?: QuotaState;
};

const ORDINALS = ["", "1st", "2nd", "3rd", "4th", "5th"];
const ordinal = (position: number) => ORDINALS[position] ?? `${position}th`;

function ChampIcon({ name, icon, size }: { name: string; icon: string; size: number }) {
  if (icon) return <img src={icon} alt={name} title={name} width={size} height={size} className="rounded-md object-cover" style={{ width: size, height: size }} />;
  return (
    <span title={name} className="grid place-items-center rounded-md bg-white/10 font-bold text-faint"
      style={{ width: size, height: size, fontSize: size * 0.38 }}>
      {name.slice(0, 2)}
    </span>
  );
}

/** Searchable champion picker used for your champion, enemies, and teammates. */
function Picker({ value, onPick, onClear, excluded, placeholder, size = 44 }: {
  value: string | null;
  onPick: (name: string) => void;
  onClear?: () => void;
  excluded?: ReadonlySet<string>;
  placeholder: string;
  size?: number;
}) {
  const all = useMemo(() => rosterList(), []);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const picked = value ? all.find((c) => c.name === value) : null;
  const available = all.filter((c) => c.name === value || !excluded?.has(c.name));
  const results = q
    ? available.filter((c) => c.name.toLowerCase().includes(q.toLowerCase())).slice(0, 8)
    : available.slice(0, 8);

  return (
    <div className="relative">
      <div className="flex items-stretch">
        <button type="button" onClick={() => setOpen((o) => !o)}
          className={`flex items-center gap-2 border border-line bg-white/[0.03] px-2 py-1.5 text-sm transition hover:border-accent/50 ${value && onClear ? "rounded-l-lg" : "rounded-lg"}`}
          style={{ minWidth: size + 90 }}>
          {picked ? <ChampIcon name={picked.name} icon={picked.icon} size={size} /> :
            <span className="grid place-items-center rounded-md bg-white/5 text-faint" style={{ width: size, height: size }}>+</span>}
          <span className={picked ? "font-medium" : "text-faint"}>{picked?.name ?? placeholder}</span>
        </button>
        {value && onClear && (
          <button type="button" onClick={() => { onClear(); setOpen(false); setQ(""); }}
            aria-label={`Remove ${value}`} title={`Remove ${value}`}
            className="rounded-r-lg border border-l-0 border-line bg-white/[0.03] px-2 text-lg text-faint transition hover:border-red-400/50 hover:text-red-300">
            X
          </button>
        )}
      </div>
      {open && (
        <div className="glass-menu absolute z-30 mt-1 w-56 rounded-xl p-2">
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

/** Shown when the day's generations are spent. Signing in with Google buys a
 *  second allowance, so that is the offer; once signed in there is nothing left
 *  to sell and it just says when the window resets. */
function QuotaWall({ quota, signedIn, authConfigured }: {
  quota: QuotaState; signedIn: boolean; authConfigured: boolean;
}) {
  // "now" is resolved after mount: reading the clock during render would make
  // the component non-idempotent (and mismatch the server-rendered markup).
  const [hours, setHours] = useState<number | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(
      () => setHours(Math.max(1, Math.ceil((quota.resetAt - Date.now()) / 3_600_000))),
      0,
    );
    return () => window.clearTimeout(timer);
  }, [quota.resetAt]);
  const canUpgrade = !signedIn && authConfigured;
  return (
    <div className="rounded-xl border border-gold/25 bg-gold/[0.07] p-4">
      <p className="text-sm font-semibold text-gold">
        {canUpgrade
          ? `That is your ${quota.limit} free builds for today.`
          : "You have used every generation for today."}
      </p>
      <p className="mt-1 text-xs leading-relaxed text-muted">
        {canUpgrade
          ? "Sign in with Google to unlock 10 more, right now. Every generation is a real model call, which is what the cap is protecting."
          : `Your allowance resets ${hours == null ? "at midnight UTC" : `in about ${hours} hours`}. Recommended builds and the Custom Build Lab stay open in the meantime.`}
      </p>
      {canUpgrade && (
        <div className="mt-3">
          <GoogleSignInButton />
        </div>
      )}
    </div>
  );
}

/** The AI build advisor. Counter mode always adapts to the selected enemies;
 *  Studio mode generates an enemy-agnostic personal build. */
export function EnemyBuildAdvisor({ presetChampion, presetForm, initialChampion, mode = "counter", onAdviceChange, onFormChange }: {
  /** Locks the advisor to one champion (the studio embeds it this way). */
  presetChampion?: string;
  /** Transform form to generate for, when the embedder already picked one
   *  (the studio's Kayn toggle drives this so there is one control, not two). */
  presetForm?: string;
  /** Seeds the picker but leaves it changeable (used by shared /counter links). */
  initialChampion?: string;
  mode?: AdvisorMode;
  onAdviceChange?: (advice: Advice | null) => void;
  /** Reports the transform form as it changes, so an embedder can keep the
   *  panels it renders around this one on the form actually selected rather
   *  than on the base champion. */
  onFormChange?: (form: string) => void;
}) {
  const roster = useMemo(() => rosterList(), []);
  const { quota, user, authConfigured, refresh } = useAccount();
  const isCounter = mode === "counter";
  const defaultPlaystyle = isCounter ? "adaptive" : "standard";
  const seedChampion = presetChampion ?? (initialChampion && roster.some((c) => c.name === initialChampion) ? initialChampion : undefined);
  const presetRole = seedChampion ? roster.find((c) => c.name === seedChampion)?.role ?? "" : "";
  const [champ, setChamp] = useState<string | null>(seedChampion ?? null);
  const [role, setRole] = useState(presetRole);
  const [playstyle, setPlaystyle] = useState<string>(defaultPlaystyle);
  const [objective, setObjective] = useState<string>("balanced");
  const [gamePhase, setGamePhase] = useState<string>("balanced");
  const [damagePath, setDamagePath] = useState<string>("standard");
  const [championForm, setChampionForm] = useState<string>(presetForm || "shadow-assassin");
  const [enemies, setEnemies] = useState<(string | null)[]>(Array(5).fill(null));
  const [allies, setAllies] = useState<(string | null)[]>(Array(4).fill(null));
  const [aheadEnemy, setAheadEnemy] = useState<string>("");
  // Items and runes the player pins before generating; the build must contain
  // them. Item slugs (may include one boot); rune display names.
  const [lockedItems, setLockedItems] = useState<string[]>([]);
  const [lockedRunes, setLockedRunes] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [advice, setAdvice] = useState<Advice | null>(null);

  // the champion's home role, to flag off-role picks (Support Graves etc.)
  const championMeta = champ ? roster.find((c) => c.name === champ) : undefined;
  const naturalRole = championMeta?.role ?? "";
  const availablePlaystyles = playstylesFor(championMeta, mode);
  const selectedPlaystyle = availablePlaystyles.find((style) => style.key === playstyle);
  const selectedEnemies = enemies.filter((enemy): enemy is string => Boolean(enemy));
  const selectedAllies = allies.filter((ally): ally is string => Boolean(ally));
  const safeAheadEnemy = selectedEnemies.includes(aheadEnemy) ? aheadEnemy : "";
  const needsEnemy = isCounter && selectedEnemies.length === 0;
  const roleMismatch = Boolean(champ && role && naturalRole && role !== naturalRole);
  const supportsDamagePath = Boolean(champ && HYBRID_DAMAGE_CHAMPIONS.has(champ));
  const outOfBudget = Boolean(quota && quota.remaining <= 0);

  const pickChamp = (name: string) => {
    setChamp(name);
    setPlaystyle(defaultPlaystyle);
    setDamagePath("standard");
    setChampionForm("shadow-assassin");
    setEnemies((current) => current.map((enemy) => enemy === name ? null : enemy));
    setAllies((current) => current.map((ally) => ally === name ? null : ally));
    const r = roster.find((c) => c.name === name);
    if (r?.role) setRole(r.role);
  };

  const reset = () => {
    setChamp(seedChampion ?? null);
    setRole(presetRole);
    setPlaystyle(defaultPlaystyle);
    setObjective("balanced");
    setGamePhase("balanced");
    setDamagePath("standard");
    setChampionForm("shadow-assassin");
    setEnemies(Array(5).fill(null));
    setAllies(Array(4).fill(null));
    setAheadEnemy("");
    setLockedItems([]);
    setLockedRunes([]);
    setAdvice(null);
    onAdviceChange?.(null);
  };

  // Simulated progress, calibrated to what generations ACTUALLY take.
  //
  // This eased toward 92% over 30 seconds, and the note under the bar promised
  // "about 30 seconds". Measured generations run 46-66s, so the bar reached its
  // ceiling and sat there for half the wait, having already told the player it
  // was nearly done. A bar that stalls at 92% reads as broken, which is worse
  // than one that is honestly still moving.
  //
  // 55s is the middle of the measured range. The curve is deliberately slower
  // than exponential decay near the end so there is always visible movement,
  // and it still snaps to 100% the moment the response lands.
  useEffect(() => {
    if (!loading) return;
    const started = Date.now();
    const id = setInterval(() => {
      setElapsed(Math.round((Date.now() - started) / 1000));
      const t = (Date.now() - started) / EXPECTED_MS;
      setProgress(Math.min(96, 4 + 92 * (1 - Math.exp(-1.35 * t))));
    }, 250);
    return () => clearInterval(id);
  }, [loading]);

  async function generate() {
    if (!champ || needsEnemy) return;
    setProgress(4);
    setElapsed(0);
    setLoading(true);
    setAdvice(null);
    onAdviceChange?.(null);
    try {
      const res = await fetch("/api/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          champion: champ, role, playstyle, objective, gamePhase, damagePath,
          championForm: champ === "Kayn" ? championForm : "",
          aheadEnemy: isCounter ? safeAheadEnemy : "", mode,
          enemies: isCounter ? selectedEnemies : [],
          allies: isCounter ? selectedAllies : [],
          lockedItems, lockedRunes,
        }),
      });
      setProgress(100);
      const responseText = await res.text();
      if (!responseText.trim()) {
        throw new Error(`Build service returned an empty response (HTTP ${res.status}).`);
      }

      let parsed: unknown;
      try {
        parsed = JSON.parse(responseText);
      } catch {
        throw new Error(`Build service returned an unreadable response (HTTP ${res.status}).`);
      }
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error(`Build service returned an invalid response (HTTP ${res.status}).`);
      }

      const payload = parsed as Advice;
      // Belt and braces: the server is supposed to send a string here, but an
      // upstream platform error can put an OBJECT in `error`, and interpolating
      // that produced "Could not build: [object Object]".
      const reported = typeof payload.error === "string" && payload.error.trim()
        ? payload.error.trim()
        : "Build request failed";
      const nextAdvice = res.ok
        ? payload
        : { ...payload, error: `${reported} (HTTP ${res.status})` };
      setAdvice(nextAdvice);
      onAdviceChange?.(nextAdvice);
    } catch (e) {
      const nextAdvice = { error: e instanceof Error ? e.message : String(e) };
      setAdvice(nextAdvice);
      onAdviceChange?.(nextAdvice);
    } finally {
      // Pull the day's remaining allowance back down from the server so the nav
      // and the studio agree after success, a restored launch failure, or a cap.
      void refresh();
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* inputs */}
      <div className="glass space-y-4 rounded-2xl p-4">
        <div className="flex flex-wrap items-end gap-4">
          <div data-tour="your-champion">
            <p className="mb-1 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Your champion</p>
            {presetChampion ? (
              <span className="inline-block rounded-lg border border-line bg-white/[0.03] px-3 py-2 text-sm font-medium">{presetChampion}</span>
            ) : (
              <Picker value={champ} onPick={pickChamp} placeholder="Pick champion"
                excluded={new Set([...selectedEnemies, ...selectedAllies])} />
            )}
          </div>
          <div data-tour="power-spike">
            <p className="mb-1 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Power spike</p>
            <select value={gamePhase} onChange={(e) => setGamePhase(e.target.value)}
              title={GAME_PHASES.find((phase) => phase.key === gamePhase)?.description}
              className="rounded-lg border border-line bg-[#0e1322] px-2 py-2 text-sm text-text outline-none">
              {GAME_PHASES.map((phase) => <option key={phase.key} value={phase.key}>{phase.label}</option>)}
            </select>
          </div>
          {supportsDamagePath && (
            <div>
              <p className="mb-1 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Damage path</p>
              <select value={damagePath} onChange={(e) => setDamagePath(e.target.value)}
                title={DAMAGE_PATHS.find((path) => path.key === damagePath)?.description}
                className="rounded-lg border border-line bg-[#0e1322] px-2 py-2 text-sm text-text outline-none">
                {DAMAGE_PATHS.map((path) => <option key={path.key} value={path.key}>{path.label}</option>)}
              </select>
            </div>
          )}
          {champ === "Kayn" && !presetForm && (
            <div>
              <p className="mb-1 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Kayn form</p>
              <select value={championForm}
                onChange={(e) => { setChampionForm(e.target.value); onFormChange?.(e.target.value); }}
                title={KAYN_FORMS.find((form) => form.key === championForm)?.description}
                className="rounded-lg border border-line bg-[#0e1322] px-2 py-2 text-sm text-text outline-none">
                {KAYN_FORMS.map((form) => <option key={form.key} value={form.key}>{form.label}</option>)}
              </select>
            </div>
          )}
          <div data-tour="playstyle">
            <p className="mb-1 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Playstyle</p>
            <select value={playstyle} onChange={(e) => setPlaystyle(e.target.value)} title={selectedPlaystyle?.description}
              className="rounded-lg border border-line bg-[#0e1322] px-2 py-2 text-sm text-text outline-none">
              {availablePlaystyles.map((style) => <option key={style.key} value={style.key}>{style.label}</option>)}
            </select>
          </div>
          <div data-tour="objective">
            <p className="mb-1 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Optimize for</p>
            <select value={objective} onChange={(e) => setObjective(e.target.value)} title={OBJECTIVE_HELP[objective]}
              className="rounded-lg border border-line bg-[#0e1322] px-2 py-2 text-sm text-text outline-none">
              {OBJECTIVES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
          <div data-tour="role">
            <p className="mb-1 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Role</p>
            <select value={role} onChange={(e) => setRole(e.target.value)} title="Choose where you plan to play this champion"
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
        {selectedPlaystyle && (
          <div className="space-y-1 text-xs text-muted">
            <p>{selectedPlaystyle.description}</p>
            <p><span className="font-medium text-text">Power spike:</span> {GAME_PHASES.find((phase) => phase.key === gamePhase)?.description}</p>
            {supportsDamagePath && <p><span className="font-medium text-text">Damage path:</span> {DAMAGE_PATHS.find((path) => path.key === damagePath)?.description}</p>}
            {champ === "Kayn" && <p><span className="font-medium text-text">Form:</span> {KAYN_FORMS.find((form) => form.key === championForm)?.description}</p>}
          </div>
        )}
        {isCounter && (
          <div data-tour="enemy-team">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Enemy team (up to 5)</p>
              <span className="text-[0.65rem] text-faint">· every playstyle adapts to these picks</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {enemies.map((e, i) => (
                <Picker key={i} value={e} placeholder="Enemy" size={38}
                  excluded={new Set([
                    ...(champ ? [champ] : []),
                    ...selectedAllies,
                    ...enemies.filter((enemy, index): enemy is string => index !== i && Boolean(enemy)),
                  ])}
                  onPick={(name) => setEnemies((current) => current.map((enemy, index) => index === i ? name : enemy))}
                  onClear={() => setEnemies((current) => current.map((enemy, index) => index === i ? null : enemy))} />
              ))}
            </div>
            {needsEnemy && <p className="mt-2 text-xs text-amber-300">Select at least one enemy to generate a counter build.</p>}
            {selectedEnemies.length > 0 && (
              <div className="mt-3 max-w-sm">
                <label className="mb-1 block text-[0.65rem] font-bold uppercase tracking-wide text-faint" htmlFor="ahead-enemy">
                  Snowball threat <span className="normal-case font-normal">· optional</span>
                </label>
                <select id="ahead-enemy" value={safeAheadEnemy} onChange={(e) => setAheadEnemy(e.target.value)}
                  title="Mark an enemy who is already ahead to receive one explicit item-over-item emergency swap"
                  className="w-full rounded-lg border border-line bg-[#0e1322] px-2 py-2 text-sm text-text outline-none">
                  <option value="">No enemy is specifically ahead</option>
                  {selectedEnemies.map((enemy) => <option key={enemy} value={enemy}>{enemy} is ahead</option>)}
                </select>
              </div>
            )}
            <div className="mt-4 border-t border-line/70 pt-4" data-tour="ally-team">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Your teammates (up to 4)</p>
                <span className="text-[0.65rem] text-faint">- optional, improves team synergy and role coverage</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {allies.map((ally, i) => (
                  <Picker key={i} value={ally} placeholder="Teammate" size={38}
                    excluded={new Set([
                      ...(champ ? [champ] : []),
                      ...selectedEnemies,
                      ...allies.filter((name, index): name is string => index !== i && Boolean(name)),
                    ])}
                    onPick={(name) => setAllies((current) => current.map((currentAlly, index) => index === i ? name : currentAlly))}
                    onClear={() => setAllies((current) => current.map((currentAlly, index) => index === i ? null : currentAlly))} />
                ))}
              </div>
            </div>
          </div>
        )}
        <div data-tour="locks">
          <LockPicker
            lockedItems={lockedItems}
            lockedRunes={lockedRunes}
            onItemsChange={setLockedItems}
            onRunesChange={setLockedRunes}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2" data-tour="generate">
          <button onClick={generate} disabled={!champ || needsEnemy || loading || outOfBudget} title="Generate the optimal item order, boots, runes, and build evaluation"
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-5 py-2 text-sm font-bold text-black transition hover:opacity-90 disabled:opacity-40">
            {!loading && <Sparkles />}
            {loading ? "Building…" : "Generate optimal build"}
          </button>
          <button onClick={reset} disabled={loading}
            className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-muted transition hover:text-text disabled:opacity-40">
            Reset
          </button>
          {quota && !outOfBudget && (
            <span className="text-xs text-faint">
              <span className="font-semibold text-muted">{quota.remaining}</span> of {quota.limit} generations left today
            </span>
          )}
        </div>
        {outOfBudget && <QuotaWall quota={quota!} signedIn={Boolean(user)} authConfigured={authConfigured} />}
      </div>

      {loading && (
        <div className="glass rounded-2xl p-4">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="text-muted">
              {isCounter
                ? "Reading the enemy comp and finding the optimal build"
                : "Finding your optimal build"}…
            </span>
            <span className="font-semibold text-accent">{Math.round(progress)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
            <div className="h-full rounded-full bg-accent transition-[width] duration-300 ease-out"
              style={{ width: `${progress}%` }} />
          </div>
          <p className="mt-2 text-xs text-faint">
            {elapsed > 0 ? `${elapsed}s elapsed. ` : ""}
            This usually takes about a minute. The model reasons through your whole
            kit, the item pool and the runes before it answers.
          </p>
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
                <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">Optimal build order{isCounter ? " · vs your enemy comp" : ` · ${selectedPlaystyle?.label ?? playstyle}`}</p>
                {typeof advice.buildScore?.overall === "number" && (
                  <span className="rounded-md bg-accent/15 px-2 py-0.5 text-[0.65rem] font-bold text-accent"
                    title={advice.buildScore.reason}>
                    Build rating {advice.buildScore.overall}
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

            {advice.buildScore && (
              <div className="glass rounded-2xl p-4">
                <p className="mb-3 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Complete build evaluation</p>
                <div className="grid grid-cols-2 gap-2 text-center sm:grid-cols-4">
                  {[
                    ["Overall", advice.buildScore.overall],
                    ["Early power", advice.buildScore.earlyPower],
                    ["Burst", advice.buildScore.burst],
                    ["Sustained", advice.buildScore.sustainedDamage],
                    ["Survivability", advice.buildScore.survivability],
                    ["Mobility", advice.buildScore.mobility],
                    ["Utility", advice.buildScore.utility],
                    ["Confidence", advice.buildScore.confidence],
                  ].map(([label, value]) => (
                    <div key={String(label)} className="rounded-lg bg-white/[0.04] px-2 py-2">
                      <div className="text-lg font-bold text-accent">{value}</div>
                      <div className="text-[0.58rem] font-bold uppercase tracking-wide text-faint">{label}</div>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-sm text-muted">{advice.buildScore.reason}</p>
              </div>
            )}

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

            {advice.summoners?.length ? (
              <div className="glass rounded-2xl p-4">
                <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Summoner spells</p>
                <div className="flex flex-wrap items-center gap-2">
                  {advice.summoners.map((spell) => (
                    <span key={spell.name} className="flex items-center gap-1.5 rounded-md bg-white/5 px-2 py-1 text-sm">
                      {spell.icon && <img src={spell.icon} alt="" width={24} height={24} className="rounded" />}
                      {spell.name}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            {advice.situational?.length ? (
              <div className="glass rounded-2xl p-4">
                <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wide text-faint">
                  Situational swaps <span className="normal-case text-faint/60">· bought in place of that purchase, not added at the end</span>
                </p>
                <div className="space-y-2 text-sm">
                  {[...advice.situational]
                    .sort((left, right) => (left.atPosition ?? 9) - (right.atPosition ?? 9))
                    .map((s, i) => (
                      <div key={i} className="flex flex-wrap items-center gap-2">
                        {s.atPosition ? (
                          <span className="shrink-0 rounded-md bg-accent/15 px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-accent">
                            {ordinal(s.atPosition)} item
                          </span>
                        ) : null}
                        <img src={itemIcon(s.item)} alt={itemName(s.item)} width={24} height={24} className="rounded" />
                        <span className="font-medium">{itemName(s.item)}</span>
                        <span className="text-muted">
                          instead of {itemName(s.replaces)} · when {s.when}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            ) : null}

            {advice.situationalRunes?.length ? (
              <div className="glass rounded-2xl p-4">
                <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wide text-faint">
                  Situational runes <span className="normal-case text-faint/60">· sometimes a rune answers it cheaper than an item</span>
                </p>
                <div className="space-y-2 text-sm">
                  {advice.situationalRunes.map((s, i) => (
                    <div key={i} className="flex flex-wrap items-center gap-2">
                      {runeIcon(s.rune) && <img src={runeIcon(s.rune)!} alt="" width={22} height={22} className="rounded-full" />}
                      <span className="font-medium">{s.rune}</span>
                      <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide ${
                        s.replacesType === "item" ? "bg-gold/15 text-gold" : "bg-accent/15 text-accent"
                      }`}>
                        {s.replacesType === "item" ? "frees an item slot" : "rune swap"}
                      </span>
                      <span className="text-muted">
                        over {s.replacesLabel ?? (s.replacesType === "item" ? itemName(s.replaces) : s.replaces)} · when {s.when}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {advice.snowballSwap ? (
              <div className="rounded-2xl border border-amber-400/25 bg-amber-400/[0.06] p-4">
                <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wide text-amber-300">If {safeAheadEnemy || "the threat"} is snowballing</p>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <img src={itemIcon(advice.snowballSwap.item)} alt={itemName(advice.snowballSwap.item)} width={28} height={28} className="rounded" />
                  <span>Pick <b>{itemName(advice.snowballSwap.item)}</b> over <b>{itemName(advice.snowballSwap.replaces)}</b>.</span>
                  <span className="text-muted">{advice.snowballSwap.when}</span>
                </div>
              </div>
            ) : null}

            {advice.situationalBoots?.length ? (
              <div className="glass rounded-2xl p-4">
                <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Situational boots</p>
                <div className="space-y-1.5 text-sm">
                  {advice.situationalBoots.map((s) => (
                    <div key={s.boots} className="flex items-center gap-2">
                      <img src={itemIcon(s.boots)} alt={itemName(s.boots)} width={24} height={24} className="rounded" />
                      <span className="font-medium">{itemName(s.boots)}</span>
                      <span className="text-muted">when {s.when}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <WhyThisBuild advice={advice} />

            <div className="flex flex-wrap items-center gap-2">
              <ShareBuildButton
                path={isCounter
                  ? `/counter?champion=${encodeURIComponent(champ ?? "")}`
                  : `/build?champion=${encodeURIComponent(champ ?? "")}&tab=generate`}
                title={`${champ} build on WrTrueMeta`}
                text={isCounter
                  ? `${champ} build against ${selectedEnemies.join(", ") || "the enemy team"}, from WrTrueMeta.`
                  : `${champ} ${selectedPlaystyle?.label ?? playstyle} build from WrTrueMeta.`}
                label="Share this build"
              />
              {champ && (
                <AddToAlbumButton
                  build={{
                    champion: champ,
                    championSlug: championMeta?.slug ?? champ.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
                    source: "generated",
                    role: role || undefined,
                    variant: isCounter ? "counter" : selectedPlaystyle?.key ?? playstyle,
                    items: [
                      ...(advice.items ?? []),
                      ...(advice.bootsUpgrade ? [advice.bootsUpgrade] : advice.boots ? [advice.boots] : []),
                    ],
                    runes: advice.runes
                      ? [advice.runes.keystone, ...advice.runes.minors, advice.runes.flex].filter(Boolean)
                      : [],
                  }}
                />
              )}
            </div>

            <BuildFeedback champion={champ ?? undefined} />
          </div>
        )
      )}
    </div>
  );
}
