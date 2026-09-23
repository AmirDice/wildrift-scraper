"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { getChampions, pendingChampions, type Champion } from "@/lib/data";
import { roster } from "@/lib/threat";
import { VideoAdGate } from "@/components/video-ad-gate";
import { ChampionAvatar, TierChip } from "@/components/ui";
import { CounterReasoning, EnemyRead, type CounterSummary } from "@/components/counter-intel";
import {
  buildEnemyTraits,
  type Slot,
  DRAFT_ROLES,
  emptyDraft,
  MAX_BANS,
  metaScore,
  normaliseDraft,
  picked,
  playsRole,
  suggestBans,
  suggestPicks,
  unavailable,
  type DraftRole,
  type DraftState,
  type Suggestion,
  buildAllyNeeds,
  analyseDraft,
} from "@/lib/draft";
import itemsData from "@/data/items.json";
import runeIconsData from "@/data/rune_icons.json";

/* eslint-disable @next/next/no-img-element */

// The screen is built for a live lobby: ~30 seconds per pick, one hand on the
// phone. Tap the seat that just locked, tap the champion, and the assistant
// keeps re-ranking what YOU should pick from the champions you actually play,
// then turns the locked enemy comp into a counter build with one tap -- the
// same generator, cache and daily allowance as the Build Studio.
//
// THE BOARD IS THE CONTROL. It used to carry a row of mode tabs -- ban, my
// pick, ally, enemy -- that decided what the next tap on the roster meant, so
// recording one enemy pick was two taps in two different places, and a tap
// landing in the wrong list was silent. Now a seat IS the control: tap an
// empty seat to fill it, tap a filled one to clear it.
//
// And the roster grid is mounted ONLY while a seat is open. It was 141 avatars
// on the page at all times, every one of them a request to the CN icon CDN;
// the picker opens on your own pool (or the meta list for a seat that is not
// yours), which is a dozen or so.

/** Which seat the picker is filling. */
type SlotKind = "ban" | "me" | "ally" | "enemy";
type Target = { kind: SlotKind; index: number };

function seatLabel(t: Target): string {
  if (t.kind === "me") return "Your pick";
  if (t.kind === "ban") return `Ban ${t.index + 1}`;
  return `${t.kind === "ally" ? "Ally" : "Enemy"} ${t.index + 1}`;
}

/**
 * A colour per side of the board, so a glance tells you whose seat you are
 * looking at without reading a label: BLUE is your team, RED is theirs, GOLD
 * is the ban row. Empty seats, filled rings, the open-seat highlight, the
 * section headings and the picker all take their colour from here, because a
 * board that only colours the filled seats says nothing until it is too late
 * to matter.
 */
const SEAT_COLOURS: Record<SlotKind, {
  ring: string; idle: string; open: string; text: string; panel: string;
}> = {
  ban: {
    ring: "ring-gold/70 grayscale",
    idle: "border-dashed border-gold/35 bg-gold/[0.06] text-gold/60 hover:border-gold/80 hover:bg-gold/15 hover:text-gold",
    open: "border-gold bg-gold/20 text-gold ring-2 ring-gold",
    text: "text-gold",
    panel: "ring-gold/40",
  },
  me: {
    ring: "ring-accent",
    idle: "border-dashed border-accent/45 bg-accent/[0.06] text-accent/70 hover:border-accent hover:bg-accent/15 hover:text-accent",
    open: "border-accent bg-accent/20 text-accent ring-2 ring-accent",
    text: "text-accent",
    panel: "ring-accent/40",
  },
  ally: {
    ring: "ring-accent/50",
    idle: "border-dashed border-accent/30 bg-accent/[0.04] text-accent/55 hover:border-accent/70 hover:bg-accent/12 hover:text-accent",
    open: "border-accent bg-accent/20 text-accent ring-2 ring-accent",
    text: "text-accent",
    panel: "ring-accent/40",
  },
  enemy: {
    ring: "ring-red-500/70",
    idle: "border-dashed border-red-500/35 bg-red-500/[0.06] text-red-400/60 hover:border-red-500/80 hover:bg-red-500/15 hover:text-red-300",
    open: "border-red-500 bg-red-500/20 text-red-300 ring-2 ring-red-500",
    text: "text-red-400",
    panel: "ring-red-500/40",
  },
};

/** How many champions the picker shows before you search or ask for the rest.
 *  Enough that a lobby's likely picks are all there, few enough that opening a
 *  seat is instant on a phone. */
const PICKER_PREVIEW = 30;

const POOL_KEY = "draft:pool";
const ROLE_KEY = "draft:role";
const MAIN_ROLE_KEY = "draft:mainRole";
const STATE_KEY = "draft:state";
const DEVICE_KEY = "wrtm-device-id";

function deviceId(): string {
  try {
    let id = localStorage.getItem(DEVICE_KEY);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  } catch {
    return "draft-web";
  }
}

interface V1Item {
  slug: string;
  why?: string | null;
}
interface V1Advice {
  items?: V1Item[];
  boots?: string | null;
  bootsUpgrade?: string | null;
  bootsReason?: string | null;
  runes?: {
    keystone?: { name?: string } | string | null;
    minors?: ({ name?: string } | string)[] | null;
    treeMinors?: ({ name?: string } | string)[] | null;
    // The advisor has always returned a flex rune. This type omitted it, so
    // the page below could not render it even though the data was there.
    flex?: { name?: string } | string | null;
    primaryTree?: string | null;
  } | null;
  // The API returns {name, icon}. Typing these as bare names threw the
  // icon away at the type boundary, so no rendering code could use it.
  summoners?: ({ name?: string; icon?: string } | string)[] | null;
  situational?: { slug?: string; name?: string; when?: string }[] | null;
  counterSummary?: CounterSummary | null;
}
interface V1Response {
  build?: V1Advice;
  cached?: boolean;
  quota?: { used?: number; limit?: number };
  error?: string;
}

const ITEMS = new Map(
  (itemsData as { slug: string; name: string; icon: string }[]).map((it) => [it.slug, it]),
);

const RUNE_ICONS = runeIconsData as Record<string, string>;

/** A rune's icon, by name. Same map the Counter Builder reads; the draft page
 *  was showing bare text next to items that all had pictures. */
function runeIcon(name: string | null | undefined): string | null {
  if (!name) return null;
  return RUNE_ICONS[name] ?? null;
}

function itemName(slug: string | null | undefined): string {
  if (!slug) return "";
  return ITEMS.get(slug)?.name ?? slug.replace(/-/g, " ");
}
function itemIcon(slug: string | null | undefined): string | null {
  if (!slug) return null;
  return ITEMS.get(slug)?.icon ?? `/items/${slug}.webp`;
}
function nameOf(v: { name?: string } | string | null | undefined): string {
  if (!v) return "";
  return typeof v === "string" ? v : (v.name ?? "");
}

/** Whatever is stored under `key`, or null. Parsing is the caller's problem:
 *  the draft runs it through normaliseDraft, which is the one place that knows
 *  what a board looks like in this version. */
function loadRaw(store: "local" | "session", key: string): unknown {
  try {
    const raw = (store === "local" ? localStorage : sessionStorage).getItem(key);
    return raw ? (JSON.parse(raw) as unknown) : null;
  } catch {
    return null;
  }
}

function SuggestionCard({ s, onPick, dim = false }: {
  s: Suggestion;
  onPick: () => void;
  dim?: boolean;
}) {
  return (
    <button
      onClick={onPick}
      className={`glass-thin flex shrink-0 items-center gap-2 rounded-xl px-2.5 py-2 text-left transition hover:ring-1 hover:ring-accent/60 ${
        dim ? "opacity-70" : ""
      }`}
    >
      <ChampionAvatar champion={s.champion} size={dim ? 30 : 36} showBadges={false} />
      <span className="min-w-0">
        <span className="flex items-center gap-1.5 text-sm font-semibold">
          {s.champion.name}
          <TierChip tier={s.champion.tier} />
        </span>
        <span className="block max-w-44 truncate text-[11px] text-muted">
          {s.reasons.join(" · ") || `${s.champion.wr}% win rate`}
        </span>
      </span>
    </button>
  );
}

export function DraftAssistant({ reader }: {
  /** A screen reader for this board, rendered above it and handed the
   *  function that fills seats. The second-screen page passes one; /draft
   *  passes nothing and is unchanged. */
  reader?: (applyScan: (scan: { bans: string[]; allies: string[]; enemies: string[] }) => void) => ReactNode;
} = {}) {
  // Live champions without a collected ladder sample still belong in champ
  // select. Their roster-backed kit can be analysed even though they stay out
  // of rankings until a trustworthy win rate exists.
  const champions = useMemo(() => [...getChampions(), ...pendingChampions()], []);
  const bySlug = useMemo(() => new Map(champions.map((c) => [c.slug, c])), [champions]);

  const [state, setState] = useState<DraftState>(emptyDraft);
  const [pool, setPool] = useState<string[]>([]);
  /** The seat the picker is filling, or null when the board is at rest. */
  const [picking, setPicking] = useState<Target | null>(null);
  const [poolOpen, setPoolOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<DraftRole | "All">("All");
  /** Whether the open picker has been asked for the whole roster. */
  const [showAll, setShowAll] = useState(false);
  /** The pool editor searches and expands on its own, so opening it does not
   *  disturb the seat the draft is in the middle of. */
  const [poolSearch, setPoolSearch] = useState("");
  const [poolShowAll, setPoolShowAll] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  /** Who the player actually is, as opposed to what this game assigned them. */
  const [mainRole, setMainRole] = useState<DraftRole | null>(null);

  const [advice, setAdvice] = useState<V1Advice | null>(null);
  const [adviceFor, setAdviceFor] = useState("");
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");
  const [quota, setQuota] = useState<{ used?: number; limit?: number } | null>(null);

  // client-only stores; render empty first so the server markup matches
  useEffect(() => {
    // normaliseDraft, not a spread over a default: a session saved before the
    // board became seat-addressed holds compact lists, and those would render
    // two allies into the first two seats and drop the rest of the board.
    setState(normaliseDraft(loadRaw("session", STATE_KEY)));
    try {
      setPool(JSON.parse(localStorage.getItem(POOL_KEY) ?? "[]") as string[]);
    } catch {}
    // Two roles, two stores. The MAIN role is who you are and lives in
    // localStorage; THIS GAME's role lives in the session draft, because
    // being filled is a property of one game and must not follow you into
    // the next. Older saves only knew one role, so it seeds the main and
    // nobody has to re-declare themselves.
    const legacyRole = localStorage.getItem(ROLE_KEY);
    const main = localStorage.getItem(MAIN_ROLE_KEY) ?? legacyRole;
    const validMain = main && (DRAFT_ROLES as string[]).includes(main)
      ? (main as DraftRole) : null;
    if (validMain) setMainRole(validMain);
    // A fresh draft starts you in your main role; a resumed one keeps
    // whatever this game assigned.
    setState((s) => (s.myRole ? s : { ...s, myRole: validMain }));
    setHydrated(true);
  }, []);
  useEffect(() => {
    if (!hydrated) return;
    try {
      sessionStorage.setItem(STATE_KEY, JSON.stringify(state));
      if (mainRole) localStorage.setItem(MAIN_ROLE_KEY, mainRole);
    } catch {}
  }, [state, mainRole, hydrated]);
  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(POOL_KEY, JSON.stringify(pool));
    } catch {}
  }, [pool, hydrated]);

  const gone = useMemo(() => unavailable(state), [state]);
  const me = state.me ? bySlug.get(state.me) : undefined;

  // The board keeps empty seats; everything that reasons about a composition
  // wants the champions actually on it.
  const allies = useMemo(() => picked(state.allies), [state.allies]);
  const enemies = useMemo(() => picked(state.enemies), [state.enemies]);
  const bans = useMemo(() => picked(state.bans), [state.bans]);

  /**
   * Autofill: this game put you somewhere other than your main role.
   *
   * It matters here because a champion pool is built around a role. A jungle
   * main filled to Support has a pool that answers a question nobody asked,
   * so the tool has to say so rather than quietly ranking four junglers for
   * a Support slot.
   */
  const filled = Boolean(mainRole && state.myRole && state.myRole !== mainRole);
  const poolCoversRole = useMemo(
    () => pool.some((slug) => {
      const c = bySlug.get(slug);
      return c ? playsRole(c, state.myRole) : false;
    }),
    [pool, bySlug, state.myRole],
  );

  // Kit facts the champion class cannot express, read off the roster. The
  // builder lives in lib/draft.ts because this was written twice -- here and
  // in the report harness -- and the copies drifted, so a trait added for one
  // was silently missing from the other.
  // What YOUR half of the draft is still missing -- read the same way the
  // enemy's is, from the roster's kit facts rather than from class alone.
  // Without it the ranking answered three yes/no questions about the ally
  // comp, a team with one of each answered no to all three, and three
  // completely different allied drafts produced identical suggestions.
  const allyNeeds = useMemo(
    () => buildAllyNeeds(allies, Object.values(roster()), bySlug),
    [allies, bySlug],
  );
  // The composition read: what they threaten, what they are trying to do, and
  // what our own four still lack. Computed once per draft rather than per
  // candidate, because none of it depends on the candidate.
  const analysis = useMemo(
    () => analyseDraft(allies, enemies, Object.values(roster())),
    [allies, enemies],
  );
  const enemyTraits = useMemo(
    () => buildEnemyTraits(enemies, Object.values(roster()), bySlug),
    [enemies, bySlug],
  );

  /**
   * Which question the suggestion panel answers, read off the board instead of
   * off a tab the player had to remember to set.
   *
   * A lobby bans before it picks, so an untouched board is in the ban phase;
   * the moment anything is locked it becomes "what should I play". With a seat
   * open, the seat decides: a ban seat wants ban targets.
   */
  const banPhase = !state.me && allies.length === 0 && enemies.length === 0
    && bans.length < MAX_BANS;
  const suggestKind: "ban" | "pick" | null = picking
    ? (picking.kind === "ban" ? "ban" : picking.kind === "me" ? "pick" : null)
    : state.me ? null : banPhase ? "ban" : "pick";

  const suggestions = useMemo(() => {
    if (suggestKind === "ban") return suggestBans(state, pool, champions);
    if (suggestKind === "pick") {
      return suggestPicks(state, pool, champions, bySlug, 6, enemyTraits, allyNeeds, analysis);
    }
    return [];
  }, [suggestKind, state, pool, champions, bySlug, enemyTraits, allyNeeds, analysis]);

  /**
   * The other question. "Strongest pick in the game" and "strongest pick I
   * can actually play" are different answers, and a player with a four
   * champion jungle pool needs the second one -- but still deserves to see
   * what they are giving up by not owning the first.
   */
  const overallPicks = useMemo(() => {
    if (suggestKind !== "pick" || pool.length === 0) return [];
    // Filled into a role the pool does not cover, the "outside your pool"
    // list stops being a curiosity and becomes the actual answer, so it gets
    // more of them.
    const limit = poolCoversRole ? 4 : 6;
    return suggestPicks(state, [], champions, bySlug, limit, enemyTraits, allyNeeds, analysis)
      .filter((s) => !pool.includes(s.champion.slug));
  }, [suggestKind, state, pool, champions, bySlug, enemyTraits, allyNeeds, analysis, poolCoversRole]);

  const seatsOf = (kind: SlotKind) =>
    kind === "ban" ? state.bans : kind === "ally" ? state.allies : state.enemies;

  /** The next seat of the same kind still empty, ignoring the one being filled
   *  right now. Bans and enemy picks arrive in runs, so the picker walks along
   *  the row rather than making the player re-open it per seat. */
  function nextEmpty(t: Target): Target | null {
    if (t.kind === "me") return null;
    const seats = seatsOf(t.kind);
    for (let i = 0; i < seats.length; i++) {
      if (i !== t.index && !seats[i]) return { kind: t.kind, index: i };
    }
    return null;
  }

  /** Put a champion in a seat. Duplicate BANS are allowed on purpose -- both
   *  teams can ban the same champion -- but nothing else can be taken twice. */
  function place(slug: string, target: Target) {
    if (target.kind !== "ban" && gone.has(slug)) return;
    setState((s) => {
      if (target.kind === "me") return { ...s, me: slug };
      const key = target.kind === "ban" ? "bans" : target.kind === "ally" ? "allies" : "enemies";
      const seats = [...s[key]];
      seats[target.index] = slug;
      return { ...s, [key]: seats };
    });
    const next = nextEmpty(target);
    setPicking(next);
    setSearch("");
    if (!next) setShowAll(false);
  }

  function clearSeat(t: Target) {
    setState((s) => {
      if (t.kind === "me") return { ...s, me: null };
      const key = t.kind === "ban" ? "bans" : t.kind === "ally" ? "allies" : "enemies";
      const seats = [...s[key]];
      seats[t.index] = null;
      return { ...s, [key]: seats };
    });
    if (t.kind === "me") {
      setAdvice(null);
      setAdviceFor("");
    }
  }

  function openSeat(t: Target) {
    setPicking((cur) => (cur && cur.kind === t.kind && cur.index === t.index ? null : t));
    setSearch("");
    setShowAll(false);
  }

  /**
   * Fill the board from a screen read.
   *
   * FILLS EMPTY SEATS ONLY, and never clears one. A read is evidence, not the
   * truth: it sees part of a draft, it can miss a seat, and a live mirror
   * re-reads every 600ms. Letting each read rewrite the board would undo the
   * player's own corrections a second after they made them, and would flicker
   * a champion out of a seat the moment a frame missed it. So a scan can only
   * ever add, and anything wrong is one tap to remove.
   *
   * Your own pick is left alone: the reader sees five allies and cannot tell
   * which is you. Anything already on the board is skipped, so scanning twice
   * changes nothing.
   */
  const applyScan = useCallback((scan: { bans: string[]; allies: string[]; enemies: string[] }) => {
    const slugOf = (name: string) =>
      champions.find((c) => c.name === name)?.slug ?? null;
    setState((s) => {
      const taken = new Set<string>([
        ...picked(s.bans), ...picked(s.allies), ...picked(s.enemies), ...(s.me ? [s.me] : []),
      ]);
      const fill = (seats: Slot[], names: string[], allowDuplicates: boolean) => {
        const next = [...seats];
        for (const name of names) {
          const slug = slugOf(name);
          if (!slug || (!allowDuplicates && taken.has(slug))) continue;
          const at = next.findIndex((x) => !x);
          if (at === -1) break;
          next[at] = slug;
          taken.add(slug);
        }
        return next;
      };
      return {
        ...s,
        // Bans allow duplicates on the board, but a scan of the same strip
        // twice must not add the same champion twice, so they are tracked too.
        bans: fill(s.bans, scan.bans, false),
        allies: fill(s.allies, scan.allies, false),
        enemies: fill(s.enemies, scan.enemies, false),
      };
    });
  }, [champions]);

  function reset() {
    setState((s) => ({ ...emptyDraft(), myRole: s.myRole }));
    setAdvice(null);
    setAdviceFor("");
    setGenError("");
    setPicking(null);
    setSearch("");
    setShowAll(false);
  }

  /** The counter build itself, from the same generator, cache and daily
   *  allowance as the Build Studio. There is no standard build on this page any
   *  more: someone who has tapped their opponents in is asking what beats THOSE
   *  five, and a generic build sitting above the answer only delayed it. */
  async function generate() {
    if (!me || generating) return;
    setGenerating(true);
    setGenError("");
    try {
      const res = await fetch("/api/v1/build", {
        method: "POST",
        headers: { "content-type": "application/json", "x-device-id": deviceId() },
        body: JSON.stringify({
          champion: me.name,
          role: state.myRole ?? undefined,
          mode: enemies.length ? "counter" : "studio",
          enemies: enemies.map((s) => bySlug.get(s)?.name ?? s),
        }),
      });
      const data = (await res.json()) as V1Response;
      if (!res.ok || data.error || !data.build) {
        setGenError(data.error ?? "The generator is busy; try again in a moment.");
      } else {
        setAdvice(data.build);
        setAdviceFor(`${me.slug}|${enemies.join(",")}`);
      }
      if (data.quota) setQuota(data.quota);
    } catch {
      setGenError("Could not reach the generator; check your connection.");
    } finally {
      setGenerating(false);
    }
  }

  const adviceStale = advice != null && adviceFor !== `${state.me}|${enemies.join(",")}`;

  /** The first seat of a kind still empty, for the suggestion cards: tapping
   *  "worth banning" with no seat open should fill the next ban box. */
  function firstEmpty(kind: SlotKind): Target | null {
    if (kind === "me") return state.me ? null : { kind: "me", index: 0 };
    const i = seatsOf(kind).findIndex((x) => !x);
    return i === -1 ? null : { kind, index: i };
  }

  const suggestTarget: Target | null = picking
    ? picking
    : suggestKind === "ban" ? firstEmpty("ban")
    : suggestKind === "pick" ? firstEmpty("me")
    : null;

  /**
   * What the open picker shows.
   *
   * Searching, or asking for the rest, spans the whole roster. Otherwise a
   * seat opens on a SHORT list: your own pool for your own pick, the
   * strongest champions for a seat that is not yours. The page used to mount
   * all 141 avatars at all times -- 141 requests to the icon CDN before the
   * player had tapped anything -- and on a phone in a live lobby that is the
   * one cost worth cutting.
   */
  const picker = useMemo(() => {
    const q = search.trim().toLowerCase();
    const matches = champions.filter(
      (c) => (roleFilter === "All" || playsRole(c, roleFilter))
        && (!q || c.name.toLowerCase().includes(q)),
    );
    if (!picking) return { list: [] as Champion[], total: matches.length, source: "all" as const };
    if (q || showAll) return { list: matches, total: matches.length, source: "all" as const };
    if (picking.kind === "me" && pool.length > 0) {
      const mine = matches.filter((c) => pool.includes(c.slug));
      if (mine.length > 0) return { list: mine, total: matches.length, source: "pool" as const };
    }
    return {
      list: [...matches].sort((a, b) => metaScore(b) - metaScore(a)).slice(0, PICKER_PREVIEW),
      total: matches.length,
      source: "meta" as const,
    };
  }, [picking, champions, pool, roleFilter, search, showAll]);

  /** The pool editor's list: everything you already play, then the strongest
   *  of the rest, so there is always something to tap without mounting the
   *  whole roster. Searching or expanding spans all 141. */
  const poolList = useMemo(() => {
    const q = poolSearch.trim().toLowerCase();
    const matches = q ? champions.filter((c) => c.name.toLowerCase().includes(q)) : champions;
    if (q || poolShowAll) return matches;
    const mine = matches.filter((c) => pool.includes(c.slug));
    const rest = matches
      .filter((c) => !pool.includes(c.slug))
      .sort((x, y) => metaScore(y) - metaScore(x))
      .slice(0, PICKER_PREVIEW);
    return [...mine, ...rest];
  }, [champions, pool, poolSearch, poolShowAll]);

  /** One seat on the board. Filled: tap to clear. Empty: tap to open the
   *  picker on it, and tap again to close.
   *
   *  An empty seat wears a PLUS, not its seat number. The number was just a
   *  label -- it told you which box you were looking at, which you could
   *  already see -- while a plus says the box is a button. */
  const seat = (kind: SlotKind, index: number, slug: string | null, size: number) => {
    const c = slug ? bySlug.get(slug) : undefined;
    const target: Target = { kind, index };
    const open = picking?.kind === kind && picking.index === index;
    const paint = SEAT_COLOURS[kind];
    return c ? (
      <button
        key={`${kind}-${index}`}
        onClick={() => clearSeat(target)}
        title={`${c.name} — tap to remove`}
        className={`relative shrink-0 rounded-full ring-2 ${paint.ring} transition hover:opacity-70`}
      >
        <ChampionAvatar champion={c} size={size} showBadges={false} />
      </button>
    ) : (
      <button
        key={`${kind}-${index}`}
        onClick={() => openSeat(target)}
        title={`${seatLabel(target)} — tap to pick`}
        className={`grid shrink-0 place-items-center rounded-full border font-semibold leading-none transition ${
          open ? paint.open : paint.idle
        }`}
        style={{ width: size, height: size, fontSize: Math.round(size * 0.45) }}
      >
        +
      </button>
    );
  };

  /** A grid of champion icons. Used by the picker and by the pool editor, so
   *  both get the same size, the same disabled treatment and the same lazily
   *  loaded avatars. */
  const championGrid = (
    list: Champion[],
    onTap: (c: Champion) => void,
    opts: { disabled?: (c: Champion) => boolean; marked?: (c: Champion) => boolean } = {},
  ) => (
    <div className="flex flex-wrap gap-1.5">
      {list.map((c) => {
        const off = opts.disabled?.(c) ?? false;
        const on = opts.marked?.(c) ?? false;
        return (
          <button
            key={c.slug}
            onClick={() => onTap(c)}
            disabled={off}
            title={c.name}
            className={`rounded-full p-0.5 transition ${
              off ? "cursor-not-allowed opacity-25 grayscale"
                : on ? "ring-2 ring-gold"
                : "opacity-85 hover:opacity-100 hover:ring-2 hover:ring-accent/60"
            }`}
          >
            <ChampionAvatar champion={c} size={40} showBadges={false} />
          </button>
        );
      })}
      {list.length === 0 && <span className="py-3 text-sm text-faint">No champion matches.</span>}
    </div>
  );

  return (
    <div className="space-y-4">
      {reader?.(applyScan)}

      {/* role + pool + reset */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-faint">
          {filled ? "Filled to" : "My role"}
        </span>
        {DRAFT_ROLES.map((r) => (
          <button
            key={r}
            onClick={() => {
              // The first role you ever choose becomes your main; after that
              // these chips set THIS GAME's role, so being autofilled is one
              // tap and does not overwrite who you actually are.
              setState((s) => ({ ...s, myRole: s.myRole === r ? null : r }));
              if (!mainRole) setMainRole(r);
            }}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
              state.myRole === r ? "bg-accent text-white" : "glass text-muted hover:text-text"
            }`}
            title={r === mainRole ? "your main role" : undefined}
          >
            {r === "Dragon" ? "ADC" : r}
            {r === mainRole && <span className="ml-1 text-[9px] opacity-70">main</span>}
          </button>
        ))}
        <span className="grow" />
        <button
          onClick={() => setPoolOpen((v) => !v)}
          className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
            poolOpen ? "bg-gold/20 text-gold" : "glass text-muted hover:text-text"
          }`}
        >
          My pool ({pool.length})
        </button>
        <button onClick={reset} className="glass rounded-full px-3 py-1 text-xs font-semibold text-muted transition hover:text-text">
          Reset draft
        </button>
      </div>

      {poolOpen && (
        <div className="glass rounded-2xl p-4 ring-1 ring-gold/30">
          <p className="mb-2 text-xs text-muted">
            Tap the champions you actually play. Your pick suggestions come from this
            pool, and your own seat opens straight onto it (it is saved on this device);
            leave it empty to rank the whole roster.
          </p>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <input
              value={poolSearch}
              onChange={(e) => setPoolSearch(e.target.value)}
              placeholder="Search champions…"
              className="glass w-full max-w-xs rounded-lg px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
            />
            {pool.length > 0 && (
              <button
                onClick={() => setPool([])}
                className="glass rounded-full px-3 py-1 text-xs font-semibold text-muted transition hover:text-text"
              >
                Clear pool
              </button>
            )}
          </div>
          {/* Your pool first, so a set pool stays a short list to check; the
              rest of the roster follows only once you search for it. */}
          {championGrid(
            poolList,
            (c) => setPool((p) =>
              p.includes(c.slug) ? p.filter((s) => s !== c.slug) : [...p, c.slug]),
            { marked: (c) => pool.includes(c.slug) },
          )}
          {!poolSearch.trim() && !poolShowAll && champions.length > poolList.length && (
            <button
              onClick={() => setPoolShowAll(true)}
              className="glass mt-2 w-full rounded-xl px-3 py-2 text-xs font-semibold text-muted transition hover:text-text"
            >
              Show all {champions.length} champions
            </button>
          )}
        </div>
      )}

      {/* Suggestions, ABOVE the board: this is the answer the page exists to
          give, and under a ten-box ban row plus two teams it was below the fold
          on a phone exactly when the timer was running. It wears the emphasized
          liquid-glass material for the same reason. */}
      {suggestions.length > 0 && (
        <div className="liquid-glass rounded-2xl p-3">
          <span className="text-xs font-semibold uppercase tracking-wide text-gold">
            {suggestKind === "ban" ? "Worth banning"
              : pool.length ? (poolCoversRole ? "Best from your pool" : "Your pool, off-role")
              : "Suggested picks"}
          </span>
          {suggestKind !== "ban" && pool.length > 0 && (
            <span className="ml-2 text-[11px] text-faint">
              {poolCoversRole
                ? "ranked for this game, not overall"
                : `nothing in your pool plays ${state.myRole === "Dragon" ? "ADC" : state.myRole}`}
            </span>
          )}
          {suggestKind !== "ban" && filled && (
            <p className="mt-1 text-[11px] text-amber-300">
              Filled to {state.myRole === "Dragon" ? "ADC" : state.myRole} from{" "}
              {mainRole === "Dragon" ? "ADC" : mainRole}
              {!poolCoversRole && " — the list below is what actually plays here"}
              {" "}
              <button
                onClick={() => state.myRole && setMainRole(state.myRole)}
                className="underline decoration-dotted underline-offset-2 hover:text-text"
              >
                make {state.myRole === "Dragon" ? "ADC" : state.myRole} my main
              </button>
            </p>
          )}
          <div className="-mx-1 mt-1.5 flex gap-2 overflow-x-auto pb-1">
            {suggestions.map((s) => (
              <SuggestionCard key={s.champion.slug} s={s}
                onPick={() => suggestTarget && place(s.champion.slug, suggestTarget)} />
            ))}
          </div>

          {/* The other question: what they would pick if they owned anything. */}
          {overallPicks.length > 0 && (
            <div className="mt-2 border-t border-white/10 pt-2">
              <span className={`text-[11px] font-semibold uppercase tracking-wide ${
                poolCoversRole ? "text-faint" : "text-gold"
              }`}>
                {poolCoversRole
                  ? "Stronger overall, outside your pool"
                  : `Best ${state.myRole === "Dragon" ? "ADC" : state.myRole} picks available`}
              </span>
              <div className="-mx-1 mt-1 flex gap-2 overflow-x-auto pb-1">
                {overallPicks.map((s) => (
                  <SuggestionCard key={s.champion.slug} s={s} dim
                    onPick={() => suggestTarget && place(s.champion.slug, suggestTarget)} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* the draft board, which is also the whole control surface */}
      <div className="glass space-y-3 rounded-2xl p-4">
        <div>
          <div className="mb-1.5 flex items-baseline gap-2">
            <span className={`text-xs font-semibold uppercase tracking-wide ${SEAT_COLOURS.ban.text}`}>
              Bans {bans.length}/{MAX_BANS}
            </span>
            <span className="text-[11px] text-faint">
              tap a box to fill it, tap a champion to remove
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {state.bans.map((slug, i) =>
              seat("ban", i, slug, 34))}
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <span className={`text-xs font-semibold uppercase tracking-wide ${SEAT_COLOURS.me.text}`}>My team</span>
            <div className="mt-1.5 flex items-start gap-1.5">
              {/* Your own seat says so. It is bigger and wears the solid accent
                  ring, but with the seat numbers gone in favour of a plus,
                  nothing else would name it. */}
              <span className="flex flex-col items-center gap-0.5">
                {seat("me", 0, state.me, 44)}
                <span className="text-[9px] font-bold uppercase tracking-wide text-accent">
                  you
                </span>
              </span>
              {state.allies.map((slug, i) =>
                seat("ally", i, slug, 38))}
            </div>
          </div>
          <div>
            <span className={`text-xs font-semibold uppercase tracking-wide ${SEAT_COLOURS.enemy.text}`}>Enemy team</span>
            <div className="mt-1.5 flex items-center gap-1.5">
              {state.enemies.map((slug, i) =>
                seat("enemy", i, slug, 38))}
            </div>
          </div>
        </div>
      </div>

      {/* the picker, open on one seat: mounted only while a seat is waiting */}
      {picking && (
        <div className={`glass rounded-2xl p-4 ring-1 ${SEAT_COLOURS[picking.kind].panel}`}>
          <div className="mb-2 flex items-center gap-2">
            <span className={`text-sm font-bold ${SEAT_COLOURS[picking.kind].text}`}>{seatLabel(picking)}</span>
            <span className="text-[11px] text-faint">
              {picker.source === "pool" ? "your pool"
                : picker.source === "meta" ? "strongest right now"
                : `${picker.list.length} champion${picker.list.length === 1 ? "" : "s"}`}
            </span>
            <span className="grow" />
            <button
              onClick={() => { setPicking(null); setSearch(""); setShowAll(false); }}
              className="glass rounded-full px-3 py-1 text-xs font-semibold text-muted transition hover:text-text"
            >
              Done
            </button>
          </div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search champions…"
              className="glass w-full max-w-xs rounded-lg px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
            />
            {(["All", ...DRAFT_ROLES] as const).map((r) => (
              <button
                key={r}
                onClick={() => setRoleFilter(r as DraftRole | "All")}
                className={`rounded-full px-2.5 py-1 text-xs font-semibold transition ${
                  roleFilter === r ? "bg-accent text-white" : "glass text-muted hover:text-text"
                }`}
              >
                {r === "Dragon" ? "ADC" : r}
              </button>
            ))}
          </div>
          {championGrid(
            picker.list,
            (c) => place(c.slug, picking),
            // A banned or already-locked champion cannot be picked again, but
            // both teams really can ban the same one.
            { disabled: (c) => picking.kind !== "ban" && gone.has(c.slug) },
          )}
          {picker.source !== "all" && picker.total > picker.list.length && (
            <button
              onClick={() => setShowAll(true)}
              className="glass mt-2 w-full rounded-xl px-3 py-2 text-xs font-semibold text-muted transition hover:text-text"
            >
              Show all {picker.total} champions
            </button>
          )}
        </div>
      )}

      {/* the build sheet */}
      {me && (
        <div className="glass space-y-3 rounded-2xl p-4">
          <div className="flex flex-wrap items-center gap-3">
            <ChampionAvatar champion={me} size={44} showBadges={false} />
            <div>
              <div className="flex items-center gap-2 text-lg font-bold">
                {me.name} <TierChip tier={me.tier} />
              </div>
              <div className="text-xs text-muted">
                {enemies.length
                  ? `vs ${enemies.map((s) => bySlug.get(s)?.name ?? s).join(", ")}`
                  : "tap their picks above, then build against them"}
              </div>
            </div>
          </div>

          {advice && (
            <div>
              <span className="text-xs font-semibold uppercase tracking-wide text-gold">
                Counter build{adviceStale ? " · draft changed, regenerate" : ""}
              </span>
              <div className="mt-1.5 space-y-1.5">
                {(advice.items ?? []).map((it, i) => (
                  <div key={`${it.slug}-${i}`} className="flex items-start gap-2.5">
                    {itemIcon(it.slug) && (
                      <img src={itemIcon(it.slug)!} alt="" className="h-9 w-9 shrink-0 rounded-lg border border-line" />
                    )}
                    <div className="min-w-0">
                      <div className="text-sm font-semibold">
                        {i + 1}. {itemName(it.slug)}
                      </div>
                      {it.why && <div className="text-xs text-muted">{it.why}</div>}
                    </div>
                  </div>
                ))}
                {advice.boots && (
                  <div className="text-xs text-muted">
                    <span className="font-semibold text-text">Boots</span>
                    <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1.5">
                      {[advice.boots, advice.bootsUpgrade].filter(Boolean).map((slug, i) => (
                        <span key={`${slug}-${i}`} className="flex items-center gap-1.5">
                          {i > 0 && <span className="text-faint">→</span>}
                          {itemIcon(slug) && (
                            <img src={itemIcon(slug)!} alt="" className="h-6 w-6 rounded-md border border-line" />
                          )}
                          <span>{itemName(slug)}</span>
                        </span>
                      ))}
                    </div>
                    {advice.bootsReason && <div className="mt-0.5">{advice.bootsReason}</div>}
                  </div>
                )}
                {advice.runes && (() => {
                  const keystone = nameOf(advice.runes.keystone);
                  const minors = (advice.runes.minors ?? advice.runes.treeMinors ?? [])
                    .map(nameOf)
                    .filter(Boolean);
                  const flex = nameOf(advice.runes.flex);
                  const page = [keystone, ...minors].filter(Boolean);
                  if (!page.length && !flex) return null;
                  return (
                    <div className="text-xs text-muted">
                      <span className="font-semibold text-text">Runes</span>
                      {advice.runes.primaryTree ? ` · ${advice.runes.primaryTree}` : ""}
                      <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
                        {page.map((rn, i) => (
                          <span key={`${rn}-${i}`} className="flex items-center gap-1.5">
                            {runeIcon(rn) && (
                              <img src={runeIcon(rn)!} alt="" className="h-6 w-6 rounded-full" />
                            )}
                            <span className={i === 0 ? "font-semibold text-text" : ""}>{rn}</span>
                          </span>
                        ))}
                        {flex && (
                          <span className="flex items-center gap-1.5">
                            {runeIcon(flex) && (
                              <img src={runeIcon(flex)!} alt="" className="h-6 w-6 rounded-full" />
                            )}
                            <span>
                              {flex}
                              <span className="ml-1 text-faint">(flex)</span>
                            </span>
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })()}
                {(advice.summoners ?? []).length > 0 && (
                  <div className="text-xs text-muted">
                    <span className="font-semibold text-text">Summoners</span>
                    <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
                      {(advice.summoners ?? []).map((sp, i) => {
                        const name = nameOf(sp);
                        const icon = typeof sp === "string" ? null : (sp.icon ?? null);
                        if (!name) return null;
                        return (
                          <span key={`${name}-${i}`} className="flex items-center gap-1.5">
                            {icon && <img src={icon} alt="" className="h-6 w-6 rounded-md" />}
                            <span>{name}</span>
                          </span>
                        );
                      })}
                    </div>
                  </div>
                )}
                {(advice.situational ?? []).length > 0 && (
                  <p className="text-xs text-muted">
                    <span className="font-semibold text-text">Situational:</span>{" "}
                    {(advice.situational ?? [])
                      .map((s) => `${s.name ?? itemName(s.slug)}${s.when ? ` (${s.when})` : ""}`)
                      .join(" · ")}
                  </p>
                )}
              </div>
            </div>
          )}
          {advice?.counterSummary && (
            <CounterReasoning summary={advice.counterSummary} />
          )}

          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={generate}
              disabled={generating || enemies.length === 0}
              className={`rounded-xl px-4 py-2 text-sm font-bold transition ${
                enemies.length === 0
                  ? "glass cursor-not-allowed text-faint"
                  : "bg-gold text-[#221a04] hover:opacity-90"
              } ${generating ? "opacity-60" : ""}`}
            >
              {generating
                ? "Generating…"
                : advice
                  ? "Regenerate counter build"
                  : `Counter build vs ${enemies.length || "their"} pick${enemies.length === 1 ? "" : "s"}`}
            </button>
            {generating && (
              <span className="text-xs text-muted">a fresh matchup can take 15–30 seconds; known ones are instant</span>
            )}
            {/* The pre-roll, only once a wait has actually started: a known
                matchup answers instantly, and the delay means it never sees an
                ad slot at all. Full width of the row, under the button. */}
            {generating && (
              <div className="basis-full">
                <VideoAdGate delayMs={1500} />
              </div>
            )}
            {genError && <span className="text-xs text-red-400">{genError}</span>}
            {quota && quota.limit != null && (
              <span className="text-[11px] text-faint">
                generations today: {quota.used}/{quota.limit}
              </span>
            )}
          </div>
        </div>
      )}
      {/* The read on their comp, derived locally: it is worth most DURING the
          draft, so it must not wait on a generation. It sits UNDER the build
          now -- the build is the answer, this is the reasoning behind it. */}
      {enemies.length > 0 && (
        <EnemyRead
          enemies={enemies.map((s) => bySlug.get(s)?.name ?? s)}
          myRole={state.myRole ?? ""}
        />
      )}
    </div>
  );
}
