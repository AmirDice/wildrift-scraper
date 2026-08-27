"use client";

import { useEffect, useMemo, useState } from "react";
import { getChampions, type Champion } from "@/lib/data";
import { getBuildsFor, visibleBuildVariants, type Build } from "@/lib/builds";
import { counterSwaps, roster, threatProfile, type CounterRecScored } from "@/lib/threat";
import { ChampionAvatar, TierChip } from "@/components/ui";
import { CounterReasoning, EnemyRead, type CounterSummary } from "@/components/counter-intel";
import {
  DRAFT_ROLES,
  EMPTY_DRAFT,
  MAX_BANS,
  suggestBans,
  suggestPicks,
  unavailable,
  type DraftRole,
  type DraftState,
  type Suggestion,
} from "@/lib/draft";
import itemsData from "@/data/items.json";

/* eslint-disable @next/next/no-img-element */

// The screen is built for a live lobby: ~30 seconds per pick, one hand on the
// phone. Tap what happened (bans, their picks, your team), and the assistant
// keeps re-ranking what YOU should pick from the champions you actually play,
// then turns the locked enemy comp into a counter build with one tap -- the
// same generator, cache and daily allowance as the Build Studio.

type Mode = "ban" | "me" | "ally" | "enemy";

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
  } | null;
  summoners?: ({ name?: string } | string)[] | null;
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

function load<T>(store: "local" | "session", key: string, fallback: T): T {
  try {
    const raw = (store === "local" ? localStorage : sessionStorage).getItem(key);
    return raw ? { ...fallback, ...(JSON.parse(raw) as T) } : fallback;
  } catch {
    return fallback;
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

export function DraftAssistant() {
  const champions = useMemo(() => getChampions(), []);
  const bySlug = useMemo(() => new Map(champions.map((c) => [c.slug, c])), [champions]);

  const [state, setState] = useState<DraftState>(EMPTY_DRAFT);
  const [pool, setPool] = useState<string[]>([]);
  const [mode, setMode] = useState<Mode>("ban");
  const [poolOpen, setPoolOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<DraftRole | "All">("All");
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
    setState(load("session", STATE_KEY, EMPTY_DRAFT));
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
    () => pool.some((slug) => bySlug.get(slug)?.role === state.myRole),
    [pool, bySlug, state.myRole],
  );

  // Kit facts the champion class cannot express, read off the roster.
  const enemyTraits = useMemo(() => {
    const r = roster();
    return {
      pctHp: new Set(
        Object.values(r).filter((c) => (c as { pctHpDamage?: boolean }).pctHpDamage)
          .map((c) => c.slug)),
      assassins: state.enemies
        .map((s) => bySlug.get(s))
        .filter((c) => c?.class === "Assassin").length,
    };
  }, [state.enemies, bySlug]);

  const suggestions = useMemo(() => {
    if (mode === "ban") return suggestBans(state, pool, champions);
    if (mode === "me" && !state.me) {
      return suggestPicks(state, pool, champions, bySlug, 6, enemyTraits);
    }
    return [];
  }, [mode, state, pool, champions, bySlug, enemyTraits]);

  /**
   * The other question. "Strongest pick in the game" and "strongest pick I
   * can actually play" are different answers, and a player with a four
   * champion jungle pool needs the second one -- but still deserves to see
   * what they are giving up by not owning the first.
   */
  const overallPicks = useMemo(() => {
    if (mode !== "me" || state.me || pool.length === 0) return [];
    // Filled into a role the pool does not cover, the "outside your pool"
    // list stops being a curiosity and becomes the actual answer, so it gets
    // more of them.
    const limit = poolCoversRole ? 4 : 6;
    return suggestPicks(state, [], champions, bySlug, limit, enemyTraits)
      .filter((s) => !pool.includes(s.champion.slug));
  }, [mode, state, pool, champions, bySlug, enemyTraits, poolCoversRole]);

  const standardBuild: Build | null = useMemo(() => {
    if (!me) return null;
    const cb = getBuildsFor(me.name);
    if (!cb) return null;
    const variant = visibleBuildVariants(cb)[0];
    return variant ? (cb.builds[variant] ?? null) : null;
  }, [me]);

  /**
   * What to change about the standard build for THIS comp, scored through the
   * fight engine in the browser.
   *
   * It costs no generation: a counter build spends one of the day's five and
   * takes up to half a minute, while this runs on the build already on screen.
   * It only reports swaps that measurably improve, and never touches the first
   * item, which is the build's core rather than a slot to trade away.
   *
   * ON DEMAND, because it is not cheap. Scoring every candidate against every
   * slot is ~125 full build evaluations and measured 1.8 SECONDS of blocked
   * main thread on a desktop; running it on every enemy tap would freeze the
   * grid mid-draft on a phone, which is the one place this has to stay quick.
   */
  const compKey = `${state.me}|${[...state.enemies].sort().join(",")}`;
  const [swaps, setSwaps] = useState<CounterRecScored[]>([]);
  const [swapsFor, setSwapsFor] = useState("");
  const [measuring, setMeasuring] = useState(false);

  function measureSwaps() {
    if (!me || !standardBuild || measuring) return;
    setMeasuring(true);
    // let the button's own state paint before the main thread goes away
    setTimeout(() => {
      try {
        const profile = threatProfile(
          state.enemies.map((s) => bySlug.get(s)?.name ?? s), 15, state.myRole ?? "");
        const items = standardBuild.coreBuild.map((it) => it.slug).filter(Boolean);
        const runeNames = [
          standardBuild.runes?.keystone?.name,
          ...(standardBuild.runes?.treeMinors ?? []).map((r) => r.name),
        ].filter((n): n is string => Boolean(n));
        setSwaps(profile
          ? counterSwaps(me.name, items, runeNames, profile, 15, items.slice(0, 1))
          : []);
      } catch {
        setSwaps([]);
      } finally {
        setSwapsFor(compKey);
        setMeasuring(false);
      }
    }, 30);
  }

  const swapsCurrent = swapsFor === compKey;

  function assign(slug: string) {
    if (mode === "ban") {
      if (state.bans.length >= MAX_BANS) return;
      // duplicates allowed on purpose: both teams can ban the same champion
      setState((s) => {
        const bans = [...s.bans, slug];
        if (bans.length >= MAX_BANS) setMode("me");
        return { ...s, bans };
      });
      return;
    }
    if (gone.has(slug)) return;
    if (mode === "me") {
      setState((s) => ({ ...s, me: slug }));
      setMode("enemy");
    } else if (mode === "ally") {
      if (state.allies.length >= 4) return;
      setState((s) => ({ ...s, allies: [...s.allies, slug] }));
    } else {
      if (state.enemies.length >= 5) return;
      setState((s) => ({ ...s, enemies: [...s.enemies, slug] }));
    }
  }

  function reset() {
    setState((s) => ({ ...EMPTY_DRAFT, myRole: s.myRole }));
    setAdvice(null);
    setAdviceFor("");
    setGenError("");
    setMode("ban");
  }

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
          mode: state.enemies.length ? "counter" : "studio",
          enemies: state.enemies.map((s) => bySlug.get(s)?.name ?? s),
        }),
      });
      const data = (await res.json()) as V1Response;
      if (!res.ok || data.error || !data.build) {
        setGenError(data.error ?? "The generator is busy; try again in a moment.");
      } else {
        setAdvice(data.build);
        setAdviceFor(`${me.slug}|${state.enemies.join(",")}`);
      }
      if (data.quota) setQuota(data.quota);
    } catch {
      setGenError("Could not reach the generator; check your connection.");
    } finally {
      setGenerating(false);
    }
  }

  const adviceStale = advice != null && adviceFor !== `${state.me}|${state.enemies.join(",")}`;

  const grid = useMemo(() => {
    const q = search.trim().toLowerCase();
    return champions.filter(
      (c) =>
        (roleFilter === "All" || c.role === roleFilter) &&
        (!q || c.name.toLowerCase().includes(q)),
    );
  }, [champions, roleFilter, search]);

  const slot = (c: Champion | undefined, ring: string, size: number, onClear?: () => void, label?: string) =>
    c ? (
      <button
        key={`${c.slug}-${label ?? ""}`}
        onClick={onClear}
        title={`${c.name} — tap to remove`}
        className={`relative shrink-0 rounded-full ring-2 ${ring} transition hover:opacity-70`}
      >
        <ChampionAvatar champion={c} size={size} showBadges={false} />
      </button>
    ) : (
      <span
        key={`empty-${label}`}
        className="grid shrink-0 place-items-center rounded-full border border-dashed border-white/20 bg-white/[0.05] text-[10px] text-faint"
        style={{ width: size, height: size }}
      >
        {label}
      </span>
    );

  return (
    <div className="space-y-4">
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
            Tap the champions you actually play. Pick suggestions come from this pool
            (it is saved on this device); leave it empty to rank the whole roster.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {champions.map((c) => (
              <button
                key={c.slug}
                onClick={() =>
                  setPool((p) => (p.includes(c.slug) ? p.filter((s) => s !== c.slug) : [...p, c.slug]))
                }
                title={c.name}
                className={`rounded-full p-0.5 transition ${
                  pool.includes(c.slug) ? "ring-2 ring-gold" : "opacity-45 hover:opacity-90"
                }`}
              >
                <ChampionAvatar champion={c} size={34} showBadges={false} />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* the draft board */}
      <div className="glass space-y-3 rounded-2xl p-4">
        <div>
          <div className="mb-1.5 flex items-baseline gap-2">
            <span className="text-xs font-semibold uppercase tracking-wide text-faint">
              Bans {state.bans.length}/{MAX_BANS}
            </span>
            <span className="text-[11px] text-faint">duplicates happen; tap one to remove it</span>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {state.bans.map((slug, i) =>
              slot(bySlug.get(slug), "ring-red-500/60 grayscale", 34, () =>
                setState((s) => ({ ...s, bans: s.bans.filter((_, j) => j !== i) })), `b${i}`),
            )}
            {Array.from({ length: MAX_BANS - state.bans.length }, (_, i) =>
              slot(undefined, "", 34, undefined, `${state.bans.length + i + 1}`),
            )}
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wide text-faint">My team</span>
            <div className="mt-1.5 flex items-center gap-1.5">
              {slot(me, "ring-accent", 44, () => { setState((s) => ({ ...s, me: null })); setAdvice(null); }, "you")}
              {state.allies.map((slug) =>
                slot(bySlug.get(slug), "ring-accent/40", 38, () =>
                  setState((s) => ({ ...s, allies: s.allies.filter((x) => x !== slug) })), slug),
              )}
              {Array.from({ length: 4 - state.allies.length }, (_, i) =>
                slot(undefined, "", 38, undefined, `a${i + 1}`),
              )}
            </div>
          </div>
          <div>
            <span className="text-xs font-semibold uppercase tracking-wide text-faint">Enemy team</span>
            <div className="mt-1.5 flex items-center gap-1.5">
              {state.enemies.map((slug) =>
                slot(bySlug.get(slug), "ring-red-500/70", 38, () =>
                  setState((s) => ({ ...s, enemies: s.enemies.filter((x) => x !== slug) })), slug),
              )}
              {Array.from({ length: 5 - state.enemies.length }, (_, i) =>
                slot(undefined, "", 38, undefined, `e${i + 1}`),
              )}
            </div>
          </div>
        </div>
      </div>

      {/* what the next tap records */}
      <div className="flex flex-wrap gap-2">
        {(
          [
            ["ban", `Ban ${state.bans.length}/${MAX_BANS}`],
            ["me", state.me ? "My pick ✓" : "My pick"],
            ["ally", `Ally ${state.allies.length}/4`],
            ["enemy", `Enemy ${state.enemies.length}/5`],
          ] as [Mode, string][]
        ).map(([m, label]) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${
              mode === m ? "bg-accent text-white" : "glass text-muted hover:text-text"
            }`}
          >
            {label}
          </button>
        ))}
        <span className="self-center text-[11px] text-faint">then tap champions below</span>
      </div>

      {/* suggestions -- the page's one must-not-miss control, so it wears the
          emphasized liquid-glass material */}
      {suggestions.length > 0 && (
        <div className="liquid-glass rounded-2xl p-3">
          <span className="text-xs font-semibold uppercase tracking-wide text-gold">
            {mode === "ban" ? "Worth banning"
              : pool.length ? (poolCoversRole ? "Best from your pool" : "Your pool, off-role")
              : "Suggested picks"}
          </span>
          {mode !== "ban" && pool.length > 0 && (
            <span className="ml-2 text-[11px] text-faint">
              {poolCoversRole
                ? "ranked for this game, not overall"
                : `nothing in your pool plays ${state.myRole === "Dragon" ? "ADC" : state.myRole}`}
            </span>
          )}
          {mode !== "ban" && filled && (
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
              <SuggestionCard key={s.champion.slug} s={s} onPick={() => assign(s.champion.slug)} />
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
                    onPick={() => assign(s.champion.slug)} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* roster grid */}
      <div className="glass rounded-2xl p-4">
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
        <div className="flex flex-wrap gap-1.5">
          {grid.map((c) => {
            const out = gone.has(c.slug) && mode !== "ban";
            return (
              <button
                key={c.slug}
                onClick={() => assign(c.slug)}
                disabled={out}
                title={c.name}
                className={`rounded-full p-0.5 transition ${
                  out ? "opacity-25 grayscale" : "opacity-85 hover:opacity-100 hover:ring-2 hover:ring-accent/60"
                }`}
              >
                <ChampionAvatar champion={c} size={40} showBadges={false} />
              </button>
            );
          })}
          {grid.length === 0 && <span className="py-3 text-sm text-faint">No champion matches.</span>}
        </div>
      </div>

      {/* The read on their comp, derived locally: it is worth most DURING the
          draft, so it must not wait on a generation. */}
      {state.enemies.length > 0 && (
        <EnemyRead
          enemies={state.enemies.map((s) => bySlug.get(s)?.name ?? s)}
          myRole={state.myRole ?? ""}
        />
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
                {state.enemies.length
                  ? `vs ${state.enemies.map((s) => bySlug.get(s)?.name ?? s).join(", ")}`
                  : "standard build — tag enemies for a counter build"}
              </div>
            </div>
          </div>

          {standardBuild && !advice && (
            <div>
              <span className="text-xs font-semibold uppercase tracking-wide text-muted">
                Standard build · instant
              </span>
              <div className="mt-1.5 flex flex-wrap items-start gap-2.5">
                {standardBuild.coreBuild.map((it, i) => (
                  <span key={it.slug} className="w-14 text-center">
                    <img src={it.icon} alt={it.name} className="mx-auto h-10 w-10 rounded-lg border border-line" />
                    <span className="mt-0.5 block text-[10px] leading-tight text-muted">
                      {i + 1}. {it.name}
                    </span>
                  </span>
                ))}
                {standardBuild.boots && (
                  <span className="w-14 text-center">
                    <img src={standardBuild.boots.icon} alt={standardBuild.boots.name} className="mx-auto h-10 w-10 rounded-lg border border-line" />
                    <span className="mt-0.5 block text-[10px] leading-tight text-muted">{standardBuild.boots.name}</span>
                  </span>
                )}
              </div>
              {standardBuild.runes?.keystone && (
                <p className="mt-2 text-xs text-muted">
                  <span className="font-semibold text-text">{standardBuild.runes.keystone.name}</span>
                  {standardBuild.runes.treeMinors?.length
                    ? ` · ${standardBuild.runes.treeMinors.map((r) => r.name).join(" · ")}`
                    : ""}
                  {standardBuild.summoners?.length
                    ? `  —  ${standardBuild.summoners.map((s) => s.name).join(" + ")}`
                    : ""}
                </p>
              )}
              {state.enemies.length > 0 && !swapsCurrent && (
                <button
                  onClick={measureSwaps}
                  disabled={measuring}
                  className="glass mt-3 w-full rounded-xl px-3 py-2 text-xs font-semibold text-accent transition hover:text-text disabled:opacity-60"
                >
                  {measuring
                    ? "Measuring against their comp…"
                    : "What should I change for this comp? · free"}
                </button>
              )}
              {swapsCurrent && swaps.length === 0 && (
                <p className="mt-3 border-t border-line/60 pt-3 text-xs text-faint">
                  Nothing in the standard build measurably improves against this comp.
                  Generate a counter build for a full rethink.
                </p>
              )}
              {swapsCurrent && swaps.length > 0 && (
                <div className="mt-3 border-t border-line/60 pt-3">
                  <p className="mb-1.5 text-[0.65rem] font-bold uppercase tracking-wide text-gold">
                    Change for this comp · free, measured here
                  </p>
                  <div className="space-y-1.5">
                    {swaps.slice(0, 3).map((s) => s.swap && (
                      <div key={s.key} className="text-xs">
                        <span className="font-semibold text-text">
                          {itemName(s.swap.add)}
                        </span>
                        <span className="text-muted"> in for {itemName(s.swap.remove)}</span>
                        <span className="ml-1 text-gold">+{s.swap.delta}</span>
                        <span className="block text-faint">{s.reason}</span>
                      </div>
                    ))}
                  </div>
                  <p className="mt-1.5 text-[0.65rem] text-faint">
                    Generate a counter build for a full rethink; these are swaps into the
                    standard one.
                  </p>
                </div>
              )}
            </div>
          )}

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
                  <p className="text-xs text-muted">
                    <span className="font-semibold text-text">Boots:</span> {itemName(advice.boots)}
                    {advice.bootsUpgrade ? ` → ${itemName(advice.bootsUpgrade)}` : ""}
                    {advice.bootsReason ? ` — ${advice.bootsReason}` : ""}
                  </p>
                )}
                {advice.runes && (
                  <p className="text-xs text-muted">
                    <span className="font-semibold text-text">Runes:</span> {nameOf(advice.runes.keystone)}
                    {(() => {
                      const minors = (advice.runes?.minors ?? advice.runes?.treeMinors ?? [])
                        .map(nameOf)
                        .filter(Boolean);
                      return minors.length ? ` · ${minors.join(" · ")}` : "";
                    })()}
                  </p>
                )}
                {(advice.summoners ?? []).length > 0 && (
                  <p className="text-xs text-muted">
                    <span className="font-semibold text-text">Summoners:</span>{" "}
                    {(advice.summoners ?? []).map(nameOf).filter(Boolean).join(" + ")}
                  </p>
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
              disabled={generating || state.enemies.length === 0}
              className={`rounded-xl px-4 py-2 text-sm font-bold transition ${
                state.enemies.length === 0
                  ? "glass cursor-not-allowed text-faint"
                  : "bg-gold text-[#221a04] hover:opacity-90"
              } ${generating ? "opacity-60" : ""}`}
            >
              {generating
                ? "Generating…"
                : advice
                  ? "Regenerate counter build"
                  : `Counter build vs ${state.enemies.length || "their"} pick${state.enemies.length === 1 ? "" : "s"}`}
            </button>
            {generating && (
              <span className="text-xs text-muted">a fresh matchup can take 15–30 seconds; known ones are instant</span>
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
    </div>
  );
}
