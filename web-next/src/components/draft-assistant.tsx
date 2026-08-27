"use client";

import { useEffect, useMemo, useState } from "react";
import { getChampions, type Champion } from "@/lib/data";
import { getBuildsFor, visibleBuildVariants, type Build } from "@/lib/builds";
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
    const role = localStorage.getItem(ROLE_KEY);
    if (role && (DRAFT_ROLES as string[]).includes(role)) {
      setState((s) => ({ ...s, myRole: role as DraftRole }));
    }
    setHydrated(true);
  }, []);
  useEffect(() => {
    if (!hydrated) return;
    try {
      sessionStorage.setItem(STATE_KEY, JSON.stringify(state));
      if (state.myRole) localStorage.setItem(ROLE_KEY, state.myRole);
    } catch {}
  }, [state, hydrated]);
  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(POOL_KEY, JSON.stringify(pool));
    } catch {}
  }, [pool, hydrated]);

  const gone = useMemo(() => unavailable(state), [state]);
  const me = state.me ? bySlug.get(state.me) : undefined;

  const suggestions = useMemo(() => {
    if (mode === "ban") return suggestBans(state, pool, champions);
    if (mode === "me" && !state.me) return suggestPicks(state, pool, champions, bySlug);
    return [];
  }, [mode, state, pool, champions, bySlug]);

  const standardBuild: Build | null = useMemo(() => {
    if (!me) return null;
    const cb = getBuildsFor(me.name);
    if (!cb) return null;
    const variant = visibleBuildVariants(cb)[0];
    return variant ? (cb.builds[variant] ?? null) : null;
  }, [me]);

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
        <span className="text-xs font-semibold uppercase tracking-wide text-faint">My role</span>
        {DRAFT_ROLES.map((r) => (
          <button
            key={r}
            onClick={() => setState((s) => ({ ...s, myRole: s.myRole === r ? null : r }))}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
              state.myRole === r ? "bg-accent text-white" : "glass text-muted hover:text-text"
            }`}
          >
            {r === "Dragon" ? "ADC" : r}
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
            {mode === "ban" ? "Worth banning" : pool.length ? "From your pool" : "Suggested picks"}
          </span>
          <div className="-mx-1 mt-1.5 flex gap-2 overflow-x-auto pb-1">
            {suggestions.map((s) => (
              <button
                key={s.champion.slug}
                onClick={() => assign(s.champion.slug)}
                className="glass-thin flex shrink-0 items-center gap-2 rounded-xl px-2.5 py-2 text-left transition hover:ring-1 hover:ring-accent/60"
              >
                <ChampionAvatar champion={s.champion} size={36} showBadges={false} />
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
            ))}
          </div>
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
