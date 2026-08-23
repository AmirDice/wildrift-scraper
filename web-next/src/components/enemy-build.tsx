"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { rosterList, type RosterChampion } from "@/lib/threat";
import { GlassSlider } from "@/components/glass-slider";
import engineData from "@/data/engine.json";
import playstyleData from "@/data/playstyles.json";
import { DAMAGE_PATHS, GAME_PHASES, HYBRID_DAMAGE_CHAMPIONS, KAYN_FORMS } from "@/lib/build-options";
import { useAccount, type QuotaState } from "@/components/account-provider";
import { GoogleSignInButton } from "@/components/google-sign-in";
import { BuildFeedback } from "@/components/build-feedback";
import { ShareBuildButton, track } from "@/components/share-build";
import { ShareSnapshotButton } from "@/components/share-snapshot";
import { BuildStages } from "@/components/build-stages";
import { WhyNotPanel } from "@/components/why-not-panel";
import { CURRENT_PATCH } from "@/lib/patch";
import { AddToAlbumButton } from "@/components/add-to-album";
import { LockPicker } from "@/components/lock-picker";
import { Tip } from "@/components/build-view";
import { Disclosure } from "@/components/ui";
import { SIGNED_IN_DAILY_BUILDS } from "@/lib/quota-limits";

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

/** The player's own rank bracket. Spoken as ranks because that is the language
 *  players use; sent as skill levels because that is what the advisor acts on.
 *  The middle is the default and sends nothing -- the site cannot verify the
 *  claim, so only the two ends are worth stating. */
const SKILL_LEVELS = [
  { key: "developing", label: "Emerald & below", description: "Forgiving, reliable choices: no stack-or-nothing keystones, no razor timing windows. The build should hold up in a rough game." },
  { key: "average", label: "Diamond - Master", description: "The standard optimisation. No adjustment either way." },
  { key: "high", label: "Grandmaster+", description: "Execution-gated, snowball-scaling choices are on the table: Dark Harvest where stacking is realistic, stacking items, greedy timings a skilled pilot converts." },
] as const;

/**
 * The items this one multiplies, or is multiplied by.
 *
 * A per-item score cannot say "this is worth more BECAUSE that is also in the
 * build", so the advisor returns the pairing as its own field and this renders
 * it. Slugs outside the shown build are dropped: the field is defined over the
 * final five, and naming a seventh item here reads as a mistake rather than as
 * information.
 */
function Pairing({ partners, inBuild }: { partners: string[]; inBuild: Set<string> }) {
  const shown = partners.filter((slug) => inBuild.has(slug));
  if (shown.length === 0) return null;
  return (
    <span className="mt-1 flex flex-wrap items-center gap-1">
      <span className="text-[0.6rem] font-bold uppercase tracking-wide text-faint">Pairs with</span>
      {shown.map((slug) => (
        <span key={slug}
          className="inline-flex items-center gap-1 rounded-md bg-white/[0.06] py-0.5 pl-0.5 pr-1.5 text-[0.7rem] text-muted">
          <img src={itemIcon(slug)} alt="" width={16} height={16}
            className="rounded-sm ring-1 ring-white/10" loading="lazy" />
          {itemName(slug)}
        </span>
      ))}
    </span>
  );
}

function WhyRow({ icon, round, name, reason, partners, inBuild }: {
  icon?: string | null; round?: boolean; name: string; reason: string;
  partners?: string[]; inBuild?: Set<string>;
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
        {partners && inBuild ? <Pairing partners={partners} inBuild={inBuild} /> : null}
      </span>
    </li>
  );
}

/**
 * How to play the build that was just generated.
 *
 * "Why this build" explains the choices; this explains what to do with them.
 * They are different questions and a player asked for both -- the reasoning is
 * what you read once, this is what you read before a game.
 *
 * Rendered above the reasoning for that reason, and open by default like every
 * other result panel.
 */
const GUIDE_SECTIONS = [
  ["earlyGame", "Early game", "text-emerald-300"],
  ["powerSpike", "Your power spike", "text-gold"],
  ["teamfight", "In a fight", "text-accent"],
  ["pitfall", "What wastes this build", "text-bad"],
] as const;

function PlayGuide({ advice }: { advice: Advice }) {
  const guide = advice.playGuide;
  const rows = GUIDE_SECTIONS
    .map(([key, label, tone]) => ({ label, tone, text: (guide?.[key] ?? "").trim() }))
    .filter((row) => row.text);
  if (!rows.length) return null;

  return (
    <details open className="glass group rounded-2xl p-4">
      <summary className="mb-3 flex cursor-pointer list-none items-center justify-between gap-2">
        <span className="min-w-0">
          <span className="block text-sm font-bold text-text">How to play this build</span>
          <span className="text-xs font-normal text-faint">
            Getting the most out of these items and runes
          </span>
        </span>
        <Disclosure />
      </summary>
      <div className="space-y-3">
        {rows.map((row) => (
          <div key={row.label}>
            <p className={`text-[0.65rem] font-bold uppercase tracking-wide ${row.tone}`}>
              {row.label}
            </p>
            <p className="mt-1 text-sm leading-relaxed text-muted">{row.text}</p>
          </div>
        ))}
      </div>
    </details>
  );
}

/**
 * "Why this build" for a GENERATED build.
 *
 * The old version listed only the free-text `why` bullets. This adds the
 * per-element reasoning the advisor now returns -- item reasons from
 * candidateItemScores, the pairings from synergyWith, rune reasons from
 * runeReasons, and the boots reason -- each shown with its own icon and name,
 * so the reader can see WHICH piece each line is about rather than reading a
 * wall of prose.
 *
 * STUDIO ONLY. Counter mode neither asks for these fields nor renders them:
 * the counterSummary already explains the build against the named comp, and
 * a counter build is wanted fast.
 */
function WhyThisBuild({ advice }: { advice: Advice }) {
  const scoreBySlug = new Map(
    (advice.candidateItemScores ?? []).map((row) => [row.item, row]),
  );
  const inBuild = new Set((advice.items ?? []).filter(Boolean));
  const itemRows = (advice.items ?? [])
    .map((slug) => ({
      icon: itemIcon(slug),
      name: itemName(slug),
      reason: scoreBySlug.get(slug)?.reason ?? "",
      partners: scoreBySlug.get(slug)?.synergyWith ?? [],
      inBuild,
    }))
    .filter((row) => row.reason);

  // The reason is written for the tier-2 boots, so the row leads with them
  // and shows the upgrade as the path, instead of the upgrade's name over a
  // sentence about different boots ("Immortal Treads -- Plated Steelcaps...").
  const bootBase = advice.boots ?? advice.bootsUpgrade;
  const bootRow = bootBase && advice.bootsReason
    ? {
        icon: itemIcon(bootBase),
        name: advice.bootsUpgrade && advice.boots
          ? `${itemName(advice.boots)} \u2192 ${itemName(advice.bootsUpgrade)}`
          : itemName(bootBase),
        reason: advice.bootsUpgradeReason
          ? `${advice.bootsReason} Upgrade: ${advice.bootsUpgradeReason}`
          : advice.bootsReason,
      }
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

  // One sentence as a teaser; the full reasoning is a click away. Collapsed
  // because by this point the reader has the build, the swaps and the guide --
  // this is the "read once" layer, not the "before a game" layer.
  const previewSource = (advice.why?.[0] ?? itemRows[0]?.reason ?? "").trim();
  const preview = previewSource ? (previewSource.match(/^[^.!?]*[.!?]?/)?.[0] ?? "").trim() : "";

  return (
    <details className="glass group rounded-2xl p-4">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 group-open:mb-3">
        <span className="min-w-0">
          <span className="block text-sm font-bold text-text">Why this build works</span>
          {preview && (
            <span className="block text-xs font-normal text-faint group-open:hidden">
              {preview} <span className="font-semibold text-accent">View full reasoning</span>
            </span>
          )}
        </span>
        <Disclosure />
      </summary>
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
    </details>
  );
}

type AdvisorMode = "studio" | "counter";
type PlaystyleDefinition = { key: string; label: string; description: string; prompt: string };

const PLAYSTYLES = playstyleData.definitions as PlaystyleDefinition[];
const PLAYSTYLES_BY_CLASS = playstyleData.byClass as Record<string, string[]>;
const PLAYSTYLE_OVERRIDES = playstyleData.overrides as Record<string, string[]>;
/** Champions for whom Poke is not a playable build. See _noPokeNote. */
const NO_POKE = new Set(playstyleData.noPoke as string[]);

function playstylesFor(champion: RosterChampion | undefined, mode: AdvisorMode): PlaystyleDefinition[] {
  const allowed = champion
    ? [...(PLAYSTYLE_OVERRIDES[champion.name] ?? PLAYSTYLES_BY_CLASS[champion.class] ?? ["standard", "oneshot"])]
    : ["standard"];
  // Poke comes from the champion's CLASS, which is too coarse for it: Mage,
  // Enchanter and Marksman all grant Poke and all contain champions who cannot
  // do it. Being ranged is not the test either -- Lillia, Thresh, Rakan and
  // Vladimir all have ranged basic attacks and still fight at short range with
  // almost none of their damage coming from range. The list is classified per
  // champion by scripts/classify_range.py.
  if (champion && NO_POKE.has(champion.name)) {
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
/** The Build Bias slider's stops. Index 2 (Balanced) is the default: it adds
 *  nothing to the request, the cache key or the prompt, so leaving the slider
 *  alone is guaranteed to behave exactly like the pre-slider generator. */
const BIAS_STOPS = [
  { key: "max_durability", label: "Maximum Durability", blurb: "The most durable competitive version of this playstyle. Still not a full tank on a damage champion." },
  { key: "durability", label: "Durability Leaning", blurb: "When two viable options are close, take the safer one." },
  { key: "balanced", label: "Balanced", blurb: "The default optimisation. No lean either way." },
  { key: "damage", label: "Damage Leaning", blurb: "When two viable options are close, take the more aggressive one." },
  { key: "max_damage", label: "Maximum Damage", blurb: "As much damage as this champion can viably carry. Never an off-meta archetype." },
] as const;

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
// Minimum time a CACHED build stays behind the progress bar. Long enough to
// read as work, short enough that it never feels like a stall.
const CACHED_MIN_MS = 5_000;

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
  /** Buy the tier-3 upgrade after this many completed items; 0 means it is not
   *  worth buying this game (bootsUpgrade is absent then). Missing on builds
   *  cached before the field existed, which read as the old fixed 2. */
  bootsUpgradeAfter?: number;
  /** One line on why the enchant lands there, shown as the marker's tooltip. */
  bootsUpgradeReason?: string;
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
  /** `synergyWith` names the other items in the final five this one multiplies
   *  or is multiplied by -- the pair claim a per-item score cannot carry. */
  candidateItemScores?: { item: string; score: number; reason: string; synergyWith?: string[] }[];
  mandatoryAuditScores?: { item: string; score: number; reason: string }[];
  /** Legal-but-wasteful overlaps and thin inputs. Not failures. */
  validationWarnings?: string[];
  why?: string[];
  /** Share of the build's items also equipped by the champion's top-50
      ranked players (freshly scraped); null before that champion's first
      capture. */
  ladderAgreement?: { matched: number; of: number; score: number } | null;
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
  /** How to actually play the loadout that was just generated. */
  playGuide?: {
    earlyGame?: string;
    powerSpike?: string;
    teamfight?: string;
    pitfall?: string;
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

/** Human stat lines from the engine's stat blob, e.g. "333 HP · 30 AD". */
const STAT_LABEL: Record<string, string> = {
  hp: "HP", ad: "AD", ap: "AP", armor: "Armor", mr: "Magic Resist",
  attackSpeed: "Attack Speed", crit: "Crit", abilityHaste: "Ability Haste",
  moveSpeed: "Move Speed", mana: "Mana", manaRegen: "Mana Regen",
  lifesteal: "Lifesteal", omnivamp: "Omnivamp", physicalVamp: "Physical Vamp",
  magicPen: "Magic Pen", magicPenFlat: "Magic Pen", physicalPen: "Armor Pen",
  physicalPenFlat: "Armor Pen", tenacity: "Tenacity", healShieldPower: "Heal & Shield Power",
};

function statLines(slug: string): string[] {
  const raw = (DATA.items?.[slug] as { stats?: Record<string, { value: number; percent: boolean }> })?.stats;
  if (!raw) return [];
  return Object.entries(raw).map(([key, v]) =>
    `${v.value}${v.percent ? "%" : ""} ${STAT_LABEL[key] ?? key}`);
}

/**
 * Item and rune tooltips for the GENERATED build.
 *
 * These used to be bare `title=` attributes, which a phone cannot show at all
 * (there is no hover) and which carry no stats. The Recommended tab has had
 * proper tooltips the whole time; the generator's own strip did not, so tapping
 * an item there did nothing.
 */
function ItemTip({ slug, advice, children }: {
  slug: string; advice: Advice; children: React.ReactNode;
}) {
  const stats = statLines(slug);
  const row = (advice.candidateItemScores ?? []).find((r) => r.item === slug);
  const reason = row?.reason;
  // names only here, not icons: the tooltip is already narrow on a phone.
  const inBuild = new Set((advice.items ?? []).filter(Boolean));
  const pairs = (row?.synergyWith ?? []).filter((s) => inBuild.has(s) && s !== slug);
  return (
    <Tip
      tip={
        <>
          <span className="font-bold">{itemName(slug)}</span>
          <span className="text-gold"> · {itemCost(slug).toLocaleString()}g</span>
          {stats.length > 0 && <span className="mt-1 block text-accent">{stats.join(" · ")}</span>}
          {reason && <span className="mt-1 block text-muted">{reason}</span>}
          {pairs.length > 0 && (
            <span className="mt-1 block text-faint">
              Pairs with {pairs.map(itemName).join(", ")}
            </span>
          )}
        </>
      }
    >
      <span className="cursor-pointer">{children}</span>
    </Tip>
  );
}

function RuneTip({ name, advice, children }: {
  name: string; advice: Advice; children: React.ReactNode;
}) {
  const meta = (DATA.runes?.[name] ?? {}) as { description?: string; tree?: string; type?: string };
  const rr = advice.runeReasons;
  const page = advice.runes;
  let reason: string | undefined;
  if (page && rr) {
    if (name === page.keystone) reason = rr.keystone;
    else if (name === page.flex) reason = rr.flex;
    else {
      const i = page.minors.indexOf(name);
      if (i >= 0) reason = rr.minors?.[i];
    }
  }
  return (
    <Tip
      tip={
        <>
          <span className="font-bold">{name}</span>
          {(meta.tree || meta.type) && (
            <span className="text-faint"> · {[meta.tree, meta.type].filter(Boolean).join(" ")}</span>
          )}
          {meta.description && <span className="mt-1 block text-accent">{meta.description}</span>}
          {reason && <span className="mt-1 block text-muted">{reason}</span>}
        </>
      }
    >
      <span className="cursor-pointer">{children}</span>
    </Tip>
  );
}

/**
 * Side-by-side of the biases the player has actually generated for this
 * champion and playstyle. Nothing is generated for free here: each column
 * exists because a generation was spent on it, which keeps the comparison
 * honest and the allowance meaningful. Cells that differ from the column to
 * their left are highlighted, because "what did the slider change" is the
 * entire question.
 */
function BiasCompare({ history, ck, currentBias }: {
  history: Record<string, { ck: string; items: string[]; boots?: string; bootsUpgrade?: string; runes: string[]; score?: Advice["buildScore"] }>;
  ck: string;
  currentBias: string;
}) {
  const order = BIAS_STOPS.map((b) => b.key).filter((k) => history[k]?.ck === ck);
  if (order.length < 2) return null;
  const cols = order.map((k) => ({ key: k, label: BIAS_STOPS.find((b) => b.key === k)!.label, ...history[k] }));
  const slots = Math.max(...cols.map((c) => c.items.length));
  return (
    <details open className="glass group rounded-2xl p-4">
      <summary className="mb-3 flex cursor-pointer list-none items-center justify-between gap-2">
        <span className="min-w-0">
          <span className="block text-sm font-bold text-text">Your biases, side by side</span>
          <span className="text-xs font-normal text-faint">
            Only the builds you generated; highlighted cells are what the slider changed
          </span>
        </span>
        <span aria-hidden className="shrink-0 text-accent transition group-open:rotate-180">v</span>
      </summary>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-xs">
          <thead>
            <tr className="border-b border-line text-left text-[0.6rem] uppercase tracking-wide text-faint">
              <th className="py-1.5 pr-2">Slot</th>
              {cols.map((c) => (
                <th key={c.key} className={`py-1.5 pr-2 ${c.key === currentBias ? "text-accent" : ""}`}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: slots }, (_, i) => (
              <tr key={i} className="border-b border-line/40">
                <td className="py-1.5 pr-2 font-bold text-faint">{i + 1}</td>
                {cols.map((c, ci) => {
                  const slug = c.items[i];
                  const differs = ci > 0 && slug !== cols[ci - 1].items[i];
                  return (
                    <td key={c.key} className={`py-1.5 pr-2 ${differs ? "font-bold text-gold" : "text-muted"}`}>
                      {slug ? (
                        <span className="inline-flex items-center gap-1.5">
                          <img src={itemIcon(slug)} alt="" width={20} height={20} className="rounded" />
                          <span className="max-w-[9rem] truncate">{itemName(slug)}</span>
                        </span>
                      ) : "-"}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr className="border-b border-line/40">
              <td className="py-1.5 pr-2 font-bold text-faint">Boots</td>
              {cols.map((c, ci) => {
                const b = c.bootsUpgrade || c.boots || "";
                const prev = cols[ci - 1];
                const differs = ci > 0 && b !== (prev.bootsUpgrade || prev.boots || "");
                return (
                  <td key={c.key} className={`py-1.5 pr-2 ${differs ? "font-bold text-gold" : "text-muted"}`}>
                    {b ? itemName(b) : "-"}
                  </td>
                );
              })}
            </tr>
            {cols.some((c) => c.score) && (
              <tr>
                <td className="py-1.5 pr-2 font-bold text-faint">Score</td>
                {cols.map((c) => (
                  <td key={c.key} className="py-1.5 pr-2 tabular-nums text-muted">
                    {c.score
                      ? `dmg ${c.score.sustainedDamage} / surv ${c.score.survivability} / early ${c.score.earlyPower}`
                      : "-"}
                  </td>
                ))}
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </details>
  );
}

/** Padlock small enough to sit on an item corner. */
function LockGlyphSmall({ open = false }: { open?: boolean }) {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="2.6" aria-hidden>
      <rect x="4" y="10" width="16" height="11" rx="2" fill={open ? "none" : "currentColor"} fillOpacity="0.35" />
      {open ? <path d="M8 10V7a4 4 0 0 1 8 0" /> : <path d="M8 10V7a4 4 0 0 1 8 0v3" />}
    </svg>
  );
}

function ItemStrip({ advice, lockedItems, onToggleLock }: {
  advice: Advice;
  /** When provided, each item gets a lock toggle: locked items are pinned for
   *  the NEXT generation, which is how "keep Trinity, rethink the rest" works
   *  without rerolling blind. */
  lockedItems?: string[];
  onToggleLock?: (slug: string) => void;
}) {
  const items = advice.items ?? [];
  // WHERE the tier-3 enchant lands is the model's call now, read from the
  // build's own power curve; 0 means it is never worth its 1000g this game.
  // Older cached builds carry no timing and read as the old fixed 2.
  const stayT2 = advice.bootsUpgradeAfter === 0;
  const upAfter = Math.min(Math.max(advice.bootsUpgradeAfter ?? 2, 1), Math.max(items.length, 1));
  return (
    <div className="flex flex-wrap items-center gap-2.5">
      {advice.boots && (
        <ItemTip slug={advice.boots} advice={advice}>
          <span className="relative inline-flex flex-col items-center">
            <img src={itemIcon(advice.boots)} alt={itemName(advice.boots)} width={40} height={40} className="rounded-lg ring-1 ring-white/10" />
            <span
              title={stayT2 ? advice.bootsUpgradeReason : undefined}
              className={`mt-0.5 text-[0.55rem] font-bold uppercase ${stayT2 ? "text-gold" : "text-faint"}`}
            >
              {stayT2 ? "T2 all game" : "T2 boots"}
            </span>
          </span>
        </ItemTip>
      )}
      {items.map((slug, i) => (
        <span key={slug} className="inline-flex items-center gap-2.5">
          <span className="inline-flex flex-col items-center">
            <ItemTip slug={slug} advice={advice}>
              <span className="relative">
                <img src={itemIcon(slug)} alt={itemName(slug)} width={46} height={46}
                     className={`rounded-lg ring-1 ${lockedItems?.includes(slug) ? "ring-2 ring-gold/70" : "ring-white/10"}`} />
                <span className="absolute -left-1.5 -top-1.5 grid h-[18px] w-[18px] place-items-center rounded-full bg-[#0e1322] text-[0.6rem] font-bold text-accent ring-1 ring-line">{i + 1}</span>
                {onToggleLock && (
                  <button
                    type="button"
                    onClick={(e) => { e.preventDefault(); e.stopPropagation(); onToggleLock(slug); }}
                    title={lockedItems?.includes(slug)
                      ? `${itemName(slug)} is locked for the next generation; click to unlock`
                      : `Lock ${itemName(slug)}: the next generation must keep it`}
                    aria-pressed={lockedItems?.includes(slug)}
                    className={`absolute -bottom-1.5 -right-1.5 grid h-[18px] w-[18px] place-items-center rounded-full ring-1 transition ${
                      lockedItems?.includes(slug)
                        ? "bg-gold text-black ring-gold"
                        : "bg-[#0e1322] text-faint ring-line hover:text-text"}`}
                  >
                    <LockGlyphSmall open={!lockedItems?.includes(slug)} />
                  </button>
                )}
              </span>
            </ItemTip>
            {/* The first three purchases are the build's core: the part worth
                finishing even in a game that ends early. */}
            {i < 3 && <span className="mt-0.5 text-[0.5rem] font-black uppercase tracking-wide text-accent/80">core</span>}
          </span>
          {advice.bootsUpgrade && i + 1 === upAfter && (
            <ItemTip slug={advice.bootsUpgrade} advice={advice}>
              <span className="relative inline-flex flex-col items-center">
                <img src={itemIcon(advice.bootsUpgrade)} alt={itemName(advice.bootsUpgrade)} width={40} height={40} className="rounded-lg ring-1 ring-gold/40" />
                <span title={advice.bootsUpgradeReason} className="mt-0.5 text-[0.55rem] font-bold uppercase text-gold">
                  {upAfter === 1 ? "T3 rush" : `T3 after ${ordinal(upAfter)}`}
                </span>
              </span>
            </ItemTip>
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
          ? `Sign in with Google to unlock ${SIGNED_IN_DAILY_BUILDS} more, right now. Every generation is a real model call, which is what the cap is protecting.`
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
export function EnemyBuildAdvisor({ presetChampion, presetForm, initialChampion, initialConfig, mode = "counter", onAdviceChange, onFormChange, deferFeedback = false }: {
  /** Prefills playstyle / role / bias from a URL (album re-optimize links and
   *  quick-start chips arrive this way). Seeds only; everything stays editable. */
  initialConfig?: { playstyle?: string; role?: string; bias?: string };
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
  /** The studio renders the feedback prompt itself, LAST on the page, after
   *  the stats drawer and the Lab hand-off it appends below this component.
   *  Inline it would sit in the middle of the page instead. */
  deferFeedback?: boolean;
}) {
  const roster = useMemo(() => rosterList(), []);
  const { quota, user, authConfigured, refresh } = useAccount();
  const isCounter = mode === "counter";
  const defaultPlaystyle = isCounter ? "adaptive" : "standard";
  const seedChampion = presetChampion ?? (initialChampion && roster.some((c) => c.name === initialChampion) ? initialChampion : undefined);
  const presetRole = seedChampion ? roster.find((c) => c.name === seedChampion)?.role ?? "" : "";
  const [champ, setChamp] = useState<string | null>(seedChampion ?? null);
  const [role, setRole] = useState(initialConfig?.role || presetRole);
  const [playstyle, setPlaystyle] = useState<string>(initialConfig?.playstyle || defaultPlaystyle);
  const [objective, setObjective] = useState<string>("balanced");
  const [gamePhase, setGamePhase] = useState<string>("balanced");
  const [skillLevel, setSkillLevel] = useState<string>("average");
  // Slider position, 0..4 into BIAS_STOPS. Deliberately NOT reset when the
  // champion changes: the lean is a preference about how to itemise, not a
  // fact about one champion. The committed ref is what analytics compares
  // against, so dragging through categories fires nothing until release.
  const initialBiasIdx = (() => {
    const i = BIAS_STOPS.findIndex((b) => b.key === initialConfig?.bias);
    return i >= 0 ? i : 2;
  })();
  const [biasIdx, setBiasIdx] = useState(initialBiasIdx);
  const committedBias = useRef(initialBiasIdx);
  /** One remembered build per bias for the CURRENT champion+playstyle, so
   *  generating a second bias produces a side-by-side instead of amnesia. */
  const [biasHistory, setBiasHistory] = useState<Record<string, {
    ck: string; items: string[]; boots?: string; bootsUpgrade?: string;
    runes: string[]; score?: Advice["buildScore"];
  }>>({});
  /** Quick-start chips: the last few generated setups, read once on mount. */
  const [recents, setRecents] = useState<{
    champ: string; slug: string; role?: string; playstyle?: string; bias?: string;
  }[]>([]);
  useEffect(() => {
    try {
      const raw = JSON.parse(localStorage.getItem("wtm_recent_setups") ?? "[]");
      if (Array.isArray(raw)) setRecents(raw.filter((r) => r?.champ && r?.slug).slice(0, 6));
    } catch { /* private mode */ }
  }, []);
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
  // Folded after a successful generation so the result leads; the summary
  // bar above brings it back. Hidden rather than unmounted, because the
  // pickers hold state (locks, enemy team) that must survive the fold.
  const [formOpen, setFormOpen] = useState(true);

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
  // `remaining` is null for unlimited accounts (Infinity does not survive
  // JSON), and in JS `null <= 0` is true -- so without the guards the more
  // privileged the account, the more locked-out the UI: the server exempted
  // admins while this line disabled their Generate button.
  const outOfBudget = Boolean(
    quota && !quota.unlimited && typeof quota.remaining === "number" && quota.remaining <= 0,
  );

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

  // Lock caps mirror the advisor's own (3 items, 2 runes): a lock the
  // generator would silently drop is worse than a refused click.
  const toggleItemLock = (slug: string) => {
    setLockedItems((prev) => prev.includes(slug)
      ? prev.filter((x) => x !== slug)
      : prev.length >= 3 ? prev : [...prev, slug]);
  };
  const toggleRuneLock = (name: string) => {
    setLockedRunes((prev) => prev.includes(name)
      ? prev.filter((x) => x !== name)
      : prev.length >= 2 ? prev : [...prev, name]);
  };

  const commitBias = (idx: number) => {
    if (committedBias.current === idx) return;
    committedBias.current = idx;
    // One event per SETTLED change. Dragging max-durability to max-damage in
    // one motion is one decision, not four.
    track("build_bias_changed");
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
    setBiasIdx(2);
    committedBias.current = 2;
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
    const startedAt = Date.now();
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
          skillLevel,
          buildBias: BIAS_STOPS[biasIdx].key,
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

      const payload = parsed as Advice & { cached?: boolean };
      // Belt and braces: the server is supposed to send a string here, but an
      // upstream platform error can put an OBJECT in `error`, and interpolating
      // that produced "Could not build: [object Object]".
      const reported = typeof payload.error === "string" && payload.error.trim()
        ? payload.error.trim()
        : "Build request failed";
      const nextAdvice = res.ok
        ? payload
        : { ...payload, error: `${reported} (HTTP ${res.status})` };
      // A cache hit returns in milliseconds, which reads as "it didn't
      // actually do anything" and undersells a build that is every bit as
      // considered as a fresh one -- somebody else simply paid for it first.
      // Hold the existing progress bar for a moment so the result lands the
      // way a generated one does. Only ever a floor: a slow cache read is not
      // delayed further, and a real generation never waits at all.
      if (res.ok && payload.cached) {
        const elapsed = Date.now() - startedAt;
        if (elapsed < CACHED_MIN_MS) {
          await new Promise((resolve) => setTimeout(resolve, CACHED_MIN_MS - elapsed));
        }
      }
      setAdvice(nextAdvice);
      onAdviceChange?.(nextAdvice);
      // The form's job is done the moment a build renders below it; folding it
      // moves the result to the top of the screen. An error keeps it open,
      // because the fix for an error lives in the form.
      if (!nextAdvice.error) {
        setFormOpen(false);
        const biasKey = BIAS_STOPS[biasIdx].key;
        const runeList = nextAdvice.runes
          ? [nextAdvice.runes.keystone, ...nextAdvice.runes.minors, nextAdvice.runes.flex].filter(Boolean)
          : [];
        setBiasHistory((h) => ({
          ...h,
          [biasKey]: {
            ck: `${champ}|${playstyle}`,
            items: [...(nextAdvice.items ?? [])],
            boots: nextAdvice.boots,
            bootsUpgrade: nextAdvice.bootsUpgrade,
            runes: runeList,
            score: nextAdvice.buildScore,
          },
        }));
        // Quick-start memory: last few setups, newest first, one per champion.
        try {
          const raw = JSON.parse(localStorage.getItem("wtm_recent_setups") ?? "[]");
          const prev = Array.isArray(raw) ? raw : [];
          const entry = {
            champ, slug: championMeta?.slug ?? champ.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
            role, playstyle, bias: biasKey, at: Date.now(),
          };
          const next = [entry, ...prev.filter((r) => r?.champ !== champ)].slice(0, 6);
          localStorage.setItem("wtm_recent_setups", JSON.stringify(next));
        } catch { /* private mode: quick-start simply stays empty */ }
      }
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
      {!isCounter && recents.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[0.65rem] font-bold uppercase tracking-wide text-muted">Quick start</span>
          {recents.map((r) => {
            const icon = roster.find((entry) => entry.name === r.champ)?.icon;
            return (
              <Link
                key={r.slug}
                href={`/build?champion=${r.slug}&tab=generate${r.playstyle ? `&variant=${encodeURIComponent(r.playstyle)}` : ""}${r.bias && r.bias !== "balanced" ? `&bias=${r.bias}` : ""}${r.role ? `&role=${encodeURIComponent(r.role)}` : ""}`}
                className="glass glass-hover inline-flex items-center gap-2 rounded-full py-1 pl-1 pr-3 text-xs font-semibold text-text transition hover:ring-1 hover:ring-accent/60"
                title={`Generate ${r.champ} with your last setup${r.bias && r.bias !== "balanced" ? ` (${r.bias.replace("_", " ")})` : ""}`}
              >
                {icon ? (
                  <img src={icon} alt="" width={22} height={22}
                       className="rounded-full object-cover ring-1 ring-white/25"
                       style={{ width: 22, height: 22 }} />
                ) : (
                  <span className="grid h-[22px] w-[22px] place-items-center rounded-full bg-white/10 text-[0.6rem] font-bold text-faint">
                    {r.champ.slice(0, 2)}
                  </span>
                )}
                {r.champ}
              </Link>
            );
          })}
        </div>
      )}
      {!formOpen && (
        <button
          type="button"
          onClick={() => setFormOpen(true)}
          className="glass glass-hover flex w-full items-center justify-between gap-3 rounded-2xl p-4 text-left"
        >
          <span className="min-w-0">
            <span className="block text-sm font-bold text-text">
              {champ ? `Build settings · ${champ}` : "Build settings"}
            </span>
            <span className="mt-0.5 block text-xs text-muted">
              Change champion, playstyle or role, then generate again.
            </span>
          </span>
          <span aria-hidden className="shrink-0 text-accent">⌄</span>
        </button>
      )}
      <div className={`glass space-y-4 rounded-2xl p-4 ${formOpen ? "" : "hidden"}`}>
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
          <div>
            <p className="mb-1 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Your rank</p>
            <select value={skillLevel} onChange={(e) => setSkillLevel(e.target.value)}
              title={SKILL_LEVELS.find((lvl) => lvl.key === skillLevel)?.description}
              className="rounded-lg border border-line bg-[#0e1322] px-2 py-2 text-sm text-text outline-none">
              {SKILL_LEVELS.map((lvl) => <option key={lvl.key} value={lvl.key}>{lvl.label}</option>)}
            </select>
          </div>
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
        {/* Build bias: a lean between damage and durability, applied inside the
            selected playstyle, never over it. The CATEGORY is the value; the
            slider is just how you pick one of five. No percentages anywhere,
            because "83% damage" would claim a precision the generator does
            not have. */}
        <div data-tour="build-bias" className="rounded-xl bg-white/[0.03] px-3 py-2.5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">
              Build bias <span className="ml-1 font-normal normal-case opacity-70">optional</span>
            </p>
            <p className={`text-xs font-bold ${biasIdx === 2 ? "text-muted" : biasIdx > 2 ? "text-gold" : "text-accent"}`}>
              {BIAS_STOPS[biasIdx].label}
            </p>
          </div>
          <div className="mt-2 flex items-center gap-3">
            <span className="shrink-0 text-[0.65rem] text-faint">More durable</span>
            <GlassSlider
              min={0} max={4} value={biasIdx}
              onDrag={setBiasIdx}
              onCommit={(idx) => { setBiasIdx(idx); commitBias(idx); }}
              ariaLabel="Build bias"
              ariaValueText={BIAS_STOPS[biasIdx].label}
              variant="bias" ticks
            />
            <span className="shrink-0 text-[0.65rem] text-faint">More damage</span>
          </div>
          <p className="mt-1.5 text-xs text-muted">{BIAS_STOPS[biasIdx].blurb}</p>
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
        {/* What this tool is actually optimising for, said before the player
            waits a minute for an answer. A blind build is solving a different
            problem from a counter build, and someone who picks Standard and
            Balanced and expects a one-shot page has been misled by silence
            rather than by anything the generator said. */}
        {!isCounter && (
          <div className="rounded-xl border border-line/70 bg-white/[0.02] p-3">
            <p className="text-xs leading-relaxed text-muted">
              <span className="font-semibold text-text">This build is made blind.</span>{" "}
              No enemy team is supplied, so it optimises for the most consistent
              first-pick loadout: the one that holds up whoever you end up against.
              Standard with everything balanced will return a solid, safe build rather
              than a one-shot or maximum-damage page, because a build that gambles is
              the wrong answer when the matchup is unknown. Pick a playstyle if you
              want it to commit to something.
            </p>
            <p className="mt-2 text-xs leading-relaxed text-muted">
              Already know who you are up against?{" "}
              <Link
                href={champ ? `/build?champion=${encodeURIComponent(champ)}&tab=counter` : "/build?tab=counter"}
                className="font-semibold text-emerald-300 underline decoration-emerald-300/40 underline-offset-2 transition hover:decoration-emerald-300"
              >
                Build against their team
              </Link>{" "}
              instead. It reads all five enemies and itemises against them specifically.
            </p>
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
              {quota.unlimited ? (
                <span className="font-semibold text-muted">Unlimited generations</span>
              ) : (
                <>
                  <span className="font-semibold text-muted">{quota.remaining}</span> of {quota.limit} generations left today
                </>
              )}
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
                {advice.ladderAgreement && advice.ladderAgreement.score >= 40 && (
                  <span className="rounded-md bg-gold/15 px-2 py-0.5 text-[0.65rem] font-bold text-gold"
                    title={`${advice.ladderAgreement.matched} of ${advice.ladderAgreement.of} items are also equipped by this champion's top-50 ranked players right now`}>
                    {advice.ladderAgreement.score}% ladder match
                  </span>
                )}
                {advice.validationErrors?.length ? (
                  <span className="rounded-md bg-amber-500/15 px-2 py-0.5 text-[0.65rem] font-bold text-amber-300" title={advice.validationErrors.join("; ")}>
                    needs review
                  </span>
                ) : null}
              </div>
              <ItemStrip advice={advice} lockedItems={lockedItems} onToggleLock={toggleItemLock} />
              {/* The padlocks on the strip lock what the build already has;
                  this picker locks anything. People who want Eclipse do not
                  reliably know it is called Eclipse, so the full catalogue is
                  browsable and searchable -- the same component, and the same
                  lock state, as the picker in the form above. */}
              <div className="mt-3">
                <LockPicker
                  lockedItems={lockedItems}
                  lockedRunes={lockedRunes}
                  onItemsChange={setLockedItems}
                  onRunesChange={setLockedRunes}
                />
              </div>
              {(lockedItems.length > 0 || lockedRunes.length > 0) && (
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-gold/25 bg-gold/[0.06] px-3 py-2">
                  <p className="text-xs text-muted">
                    <span className="font-bold text-gold">{lockedItems.length + lockedRunes.length} locked</span>
                    {" "}- the next generation keeps these and rethinks everything else
                  </p>
                  <span className="flex gap-2">
                    <button onClick={() => { setLockedItems([]); setLockedRunes([]); }}
                            className="rounded-lg border border-line px-2.5 py-1 text-xs text-muted transition hover:text-text">
                      Clear
                    </button>
                    <button onClick={generate} disabled={loading || outOfBudget}
                            className="rounded-lg bg-gold px-3 py-1 text-xs font-bold text-black transition hover:opacity-90 disabled:opacity-40">
                      Regenerate around locks
                    </button>
                  </span>
                </div>
              )}
              {(advice.runes || advice.summoners?.length) ? (
                <div className="mt-4 grid gap-4 border-t border-line/60 pt-3 md:grid-cols-[1fr_auto]">
                  {advice.runes && (
                    <div>
                      <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Runes · {advice.runes.primaryTree}</p>
                      <div className="flex flex-wrap items-center gap-2">
                        {[advice.runes.keystone, ...advice.runes.minors, advice.runes.flex].map((rn, i) => (
                          <RuneTip key={rn + i} name={rn} advice={advice}>
                            <button
                              type="button"
                              onClick={() => toggleRuneLock(rn)}
                              aria-pressed={lockedRunes.includes(rn)}
                              title={lockedRunes.includes(rn)
                                ? `${rn} is locked for the next generation; click to unlock`
                                : `Lock ${rn}: the next generation must keep it (up to 2 runes)`}
                              className={`flex items-center gap-1.5 rounded-md px-2 py-1 text-left text-xs transition ${
                                lockedRunes.includes(rn)
                                  ? "bg-gold/15 ring-1 ring-gold/60"
                                  : "bg-white/5 hover:bg-white/10"}`}
                            >
                              {runeIcon(rn) && <img src={runeIcon(rn)!} alt={rn} width={20} height={20} />}
                              {rn}{i === 0 && <span className="text-[0.6rem] font-bold text-accent"> KEY</span>}
                              {lockedRunes.includes(rn) && <LockGlyphSmall />}
                            </button>
                          </RuneTip>
                        ))}
                      </div>
                    </div>
                  )}
                  {advice.summoners?.length ? (
                    <div>
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
                </div>
              ) : null}
              {advice.items && advice.items.length > 0 && (
                <div className="mt-4 border-t border-line/60 pt-3">
                  <BuildStages
                    bare
                    name={champ ?? ""}
                    items={advice.items}
                    boots={advice.boots}
                    bootsUpgrade={advice.bootsUpgrade}
                    bootsUpgradeAfter={advice.bootsUpgradeAfter}
                    powerCurve={(advice.requestMeta as { powerCurve?: string } | undefined)?.powerCurve}
                    candidates={advice.candidateItemScores}
                    runeNames={advice.runes
                      ? [advice.runes.keystone, ...advice.runes.minors, advice.runes.flex].filter(Boolean)
                      : []}
                  />
                </div>
              )}
              {/* The ONLY save/share row, and it closes the build card: the
                  moment someone decides they like a build is right after
                  reading it, not after the analysis below. A duplicate row
                  used to sit at the very bottom of the page; it earned three
                  albums against 760 generations. */}
              {champ && (
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-line/60 pt-3">
                  <p className="text-xs text-muted">Keep this build, or send it to someone?</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <AddToAlbumButton
                      build={{
                        champion: champ,
                        championSlug: championMeta?.slug ?? champ.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
                        source: "generated",
                        role: role || undefined,
                        variant: isCounter ? "counter" : selectedPlaystyle?.key ?? playstyle,
                        bias: BIAS_STOPS[biasIdx].key,
                        patch: CURRENT_PATCH,
                        items: [
                          ...(advice.items ?? []),
                          ...(advice.bootsUpgrade ? [advice.bootsUpgrade] : advice.boots ? [advice.boots] : []),
                        ],
                        runes: advice.runes
                          ? [advice.runes.keystone, ...advice.runes.minors, advice.runes.flex].filter(Boolean)
                          : [],
                      }}
                    />
                    <ShareSnapshotButton
                      build={{
                        champion: champ,
                        championSlug: championMeta?.slug ?? champ.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
                        role: role || undefined,
                        playstyle: isCounter ? "counter" : selectedPlaystyle?.key ?? playstyle,
                        bias: BIAS_STOPS[biasIdx].key,
                        patch: CURRENT_PATCH,
                        items: advice.items ?? [],
                        boots: advice.boots,
                        bootsUpgrade: advice.bootsUpgrade,
                        bootsUpgradeAfter: advice.bootsUpgradeAfter,
                        runes: advice.runes
                          ? [advice.runes.keystone, ...advice.runes.minors, advice.runes.flex].filter(Boolean)
                          : [],
                        summoners: advice.summoners?.map((sp) => sp.name) ?? [],
                      }}
                    />
                    <ShareBuildButton
                      path={isCounter
                        ? `/build?champion=${encodeURIComponent(champ)}&tab=counter`
                        : `/build?champion=${encodeURIComponent(champ)}&tab=generate`}
                      title={`${champ} build on WrTrueMeta`}
                      text={isCounter
                        ? `${champ} build against ${selectedEnemies.join(", ") || "the enemy team"}, from WrTrueMeta.`
                        : `${champ} ${selectedPlaystyle?.label ?? playstyle} build from WrTrueMeta.`}
                      label="Share"
                    />
                  </div>
                </div>
              )}
            </div>


            {advice.items && advice.items.length > 0 && (
              <div className="glass rounded-2xl p-4">
                {!isCounter && (
                  <div className="mb-3">
                    <p className="text-sm font-bold text-text">Adapt this build</p>
                    <p className="text-xs text-faint">The default order wins most games; these swaps are for the games it does not</p>
                  </div>
                )}
                <div className="space-y-4">
                {!isCounter && advice.situational?.length ? (
              <div>
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

            {!isCounter && advice.situationalRunes?.length ? (
              <div>
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
              <div className="rounded-xl border border-amber-400/25 bg-amber-400/[0.06] p-3">
                <p className="mb-2 text-[0.65rem] font-bold uppercase tracking-wide text-amber-300">If {safeAheadEnemy || "the threat"} is snowballing</p>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <img src={itemIcon(advice.snowballSwap.item)} alt={itemName(advice.snowballSwap.item)} width={28} height={28} className="rounded" />
                  <span>Pick <b>{itemName(advice.snowballSwap.item)}</b> over <b>{itemName(advice.snowballSwap.replaces)}</b>.</span>
                  <span className="text-muted">{advice.snowballSwap.when}</span>
                </div>
              </div>
            ) : null}

            {!isCounter && advice.situationalBoots?.length ? (
              <div>
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

                <div className={isCounter && !advice.snowballSwap
                  ? "" : "border-t border-line/60 pt-4"}>
                  <WhyNotPanel
                    bare
                    champion={champ ?? ""}
                    items={advice.items}
                    situational={advice.situational}
                    situationalBoots={advice.situationalBoots}
                    boots={advice.bootsUpgrade || advice.boots}
                    runeNames={advice.runes
                      ? [advice.runes.keystone, ...advice.runes.minors, advice.runes.flex].filter(Boolean)
                      : []}
                    playstyle={isCounter ? "counter" : playstyle}
                    buildBias={BIAS_STOPS[biasIdx].key}
                  />
                </div>
                </div>
              </div>
            )}

            <PlayGuide advice={advice} />

            {!isCounter && <WhyThisBuild advice={advice} />}

            <BiasCompare history={biasHistory} ck={`${champ}|${playstyle}`} currentBias={BIAS_STOPS[biasIdx].key} />

            {!deferFeedback && <BuildFeedback champion={champ ?? undefined} />}
          </div>
        )
      )}
    </div>
  );
}
