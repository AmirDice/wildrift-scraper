"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { TierChip } from "@/components/ui";
import { ChampionCombobox } from "@/components/champion-combobox";
import { BestPlayerBuild } from "@/components/best-player-build";
import { Glyph, GLYPHS, Laurel } from "@/components/insignia";
import { TierBadge, tierParts, tierRank } from "@/components/tier-badge";
import { QueuePanel } from "@/components/queue-panel";
import type { QueueStats } from "@/lib/player-index";
import { RegionToggle, RegionComingSoon, regionFromQuery, type Region } from "@/components/region-toggle";
import type { BestPlayerPodium } from "@/lib/data";

export type SlimChampion = {
  name: string;
  slug: string;
  icon: string;
  splash: string;
  role: string;
  class: string;
  tier: string;
  wr: number;
  isHard: boolean;
  bestPlayer: { player: string; rank: number | null; confidence_wr: number | null } | null;
  bestPlayerPodium?: BestPlayerPodium | null;
  globalBestPlayerPodium?: BestPlayerPodium | null;
  podiumSkins?: { rank: number; name: string; tier: string; url: string; fallback?: string }[];
};

type Row = { r: number; p: string; w: number | null; g: number | null; s: number | null; v?: string | null; b?: number | null };

type EnrichedPlayer = Row & {
  tag: string | null;
  tier: string | null;
  level: number | null;
  /** Boosting advert: row kept, name and detail withheld. */
  hidden?: boolean | null;
  /** Permabanned: row AND name kept, but the number does not count. The
   *  opposite trade to `hidden`, and deliberately so. */
  banned?: boolean | null;
  banReason?: string | null;
  build: {
    items: { slug: string | null; name: string }[];
    runes: string[];
    spells: string[];
  } | null;
  stats: { ranked?: QueueStats; legendary?: QueueStats } | null;
};

type EnrichedPayload = { champion: string; slug: string; capturedAt: string; players: EnrichedPlayer[] };

/** The order the tabs are shown in, and the set `?region=` may select. */
const LEADERBOARD_REGIONS = ["Global", "EU", "NA", "CN"] as const;

type SortKey = "r" | "w" | "g" | "s" | "wilson" | "composite" | "tier";

/**
 * Lower bound of the 95% Wilson score interval, as a percentage.
 *
 * Shown in the table as "Best", which is the site's existing word for it: the
 * champion page has a "Best {champion} player" panel driven by this number and
 * /methodology defines the term ("'Best' means demonstrably best, not luckily
 * best"). Calling the column anything else would give one metric two names.
 *
 * Rendered as a whole number WITHOUT a percent sign, unlike the champion page
 * which prints it as a percentage. It is a win rate mathematically, but here it
 * sits directly beside the actual win rate, and "61.6%" next to "79.3%" made
 * two different quantities look like the same one.
 *
 * A mirror of web/data_loader.py::_wilson_lower_bound, same z=1.96, because the
 * site already picks each champion's "best player" this way. Two places
 * computing "who is actually best" by different formulas would disagree on the
 * same page.
 *
 * Why it beats sorting by win rate: 100% off 10 games ranks below 75% off 200,
 * which is the honest ordering. Raw win rate puts the 10-game player on top and
 * says nothing about whether the number will hold.
 *
 * Null when the win rate never extracted -- those rows sort last rather than
 * being treated as 0%, which would claim the player lost every game.
 */
function wilsonScore(winratePct: number | null, games: number | null): number | null {
  if (winratePct == null || games == null || games <= 0) return null;
  const n = games;
  const phat = Math.min(1, Math.max(0, winratePct / 100));
  const z = 1.96;
  const z2 = z * z;
  const denom = 1 + z2 / n;
  const centre = phat + z2 / (2 * n);
  const margin = z * Math.sqrt((phat * (1 - phat) + z2 / (4 * n)) / n);
  return Math.max(0, (centre - margin) / denom) * 100;
}

const num = (v: number | null | undefined) => (v == null ? -Infinity : v);

/* The enriched row for the champion's best player, or null.
 *
 * Rank alone is NOT enough to join these two sources. `bestPlayer` comes from
 * site.json (built from winrates.csv) while the enriched rows come from the
 * per-champion capture export, and the two are refreshed independently -- so
 * during a collection they routinely describe different ladders. Joining on
 * rank put "247 games" beside a name belonging to somebody else entirely.
 *
 * The name has to agree too. When it does not, the spotlight simply shows
 * less, which is the correct amount to show about a player we cannot identify.
 */
function matchBestPlayer(
  champ: SlimChampion,
  enriched: EnrichedPayload | null,
): EnrichedPlayer | null {
  const bp = champ.bestPlayer;
  if (!bp || bp.rank == null || !enriched) return null;
  const row = enriched.players.find((p) => p.r === bp.rank);
  if (!row || row.hidden) return null;
  const norm = (s: string | null | undefined) =>
    (s ?? "").toLowerCase().replace(/\s+/g, "");
  return norm(row.p) && norm(row.p) === norm(bp.player) ? row : null;
}

/* The champion header, and the crowning of its best player.
 *
 * The old version put the champion and the player side by side in the same
 * visual weight, both on top of a triple-stacked scrim that turned the splash
 * to mud. Nothing looked like the subject. This gives the two jobs different
 * treatments: the champion identifies the page, quietly; the best player is
 * the thing being celebrated, so it gets the gold, the crown, the laurels and
 * the only large number on the card.
 *
 * The splash is cropped to 25% from the top because champion art puts the
 * character's head in the upper third, and bg-center reliably decapitated
 * them.
 */
function ChampionSpotlight({
  champ,
  best,
}: {
  champ: SlimChampion;
  best: EnrichedPlayer | null;
}) {
  const bp = champ.bestPlayer;
  const facePortrait = champ.podiumSkins?.find((skin) => skin.rank === 3)?.url ?? champ.icon;
  return (
    <div className="relative mb-6 overflow-hidden rounded-2xl border border-line">
      <div
        className="absolute inset-0 bg-cover"
        style={{ backgroundImage: `url(${champ.splash})`, backgroundPosition: "center 25%" }}
      />
      {/* One horizontal scrim, not three: text sits on solid ground at the
          left while the art stays legible on the right. */}
      <div className="absolute inset-0 bg-gradient-to-r from-bg via-bg/92 to-bg/25" />
      <div className="absolute inset-0 bg-gradient-to-t from-bg via-transparent to-transparent" />
      {/* A warm glow under the spotlight panel, so the celebration reads
          before any of the words do. */}
      {bp && (
        <div
          aria-hidden
          className="pointer-events-none absolute -right-16 top-1/2 hidden h-72 w-72 -translate-y-1/2 rounded-full sm:block"
          style={{ background: "radial-gradient(circle, rgb(234 179 8 / 0.16), transparent 68%)" }}
        />
      )}

      <div className="relative flex flex-col gap-6 p-6 sm:flex-row sm:items-center sm:justify-between sm:gap-8">
        <div className="min-w-0">
          <Link
            href={`/champions/${champ.slug}`}
            className="group inline-flex items-center gap-3.5 transition hover:opacity-95"
          >
            <span
              className={`h-16 w-16 shrink-0 overflow-hidden rounded-full ${
                champ.isHard ? "ring-2 ring-bad/70" : "ring-1 ring-white/20"
              }`}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={facePortrait}
                alt=""
                width={64}
                height={64}
                className="h-full w-full object-cover"
                onError={(event) => {
                  if (event.currentTarget.src !== champ.icon) event.currentTarget.src = champ.icon;
                }}
              />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-2xl font-semibold leading-tight tracking-tight">
                {champ.name}
              </span>
              <span className="block text-xs uppercase tracking-[0.16em] text-muted">
                {champ.role} · {champ.class}
              </span>
            </span>
          </Link>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <TierChip tier={champ.tier} />
            <span className="rounded-md border border-line bg-white/[0.04] px-2 py-0.5 text-sm font-semibold tabular-nums text-accent">
              {champ.wr.toFixed(1)}% win rate
            </span>
          </div>
        </div>

        {bp && (
          <div className="relative w-full shrink-0 overflow-hidden rounded-xl border border-gold/35 bg-black/35 px-5 py-4 backdrop-blur-sm sm:w-auto sm:min-w-[17rem]">
            <div className="flex items-center gap-2 text-gold">
              <Glyph d={GLYPHS.crown} className="text-gold" size={18} />
              <span className="text-[0.65rem] font-bold uppercase tracking-[0.2em]">
                Best {champ.name}
              </span>
            </div>
            <div className="mt-2 flex items-center gap-2.5">
              <Laurel size={26} />
              <p className="min-w-0 flex-1 truncate text-2xl font-semibold leading-tight text-gold">
                {bp.player}
              </p>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-gold/20 pt-3 text-xs text-muted">
              {bp.rank != null && (
                <span className="font-semibold text-text">#{bp.rank} on the board</span>
              )}
              {/* THIS PLAYER'S OWN WIN RATE, not the shrunk one.
                  The card used to print only "67.6% adjusted", which is a
                  Bayesian estimate pulled toward the mean by how few games
                  they have played. That number exists to RANK players fairly
                  -- it is why this player was picked as the best -- but it is
                  not what they achieved, and presenting it as their win rate
                  with a word like "adjusted" invites exactly the question of
                  why we are editing somebody's record. So: their real rate
                  first, and the estimate kept beside it under the name of the
                  thing it actually measures. */}
              {best?.w != null ? (
                <span className="tabular-nums font-semibold text-text">{best.w.toFixed(1)}% win rate</span>
              ) : bp.confidence_wr != null ? (
                <span className="tabular-nums font-semibold text-text">{bp.confidence_wr.toFixed(1)}%</span>
              ) : null}
              {best?.g != null && <span className="tabular-nums">{best.g} games</span>}
              {best?.w != null && bp.confidence_wr != null && (
                <span className="tabular-nums" title="Win rate adjusted for how many games it is based on. Used to rank players against each other, so a 100% run over 5 games does not outrank a long record.">
                  {bp.confidence_wr.toFixed(1)}% confidence
                </span>
              )}
              {best?.tier && <TierBadge tier={best.tier} size={18} />}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** A compact context strip keeps the selected champion visible without
 * competing with the podium's hero treatment. */
function ChampionContextBar({ champ, best }: { champ: SlimChampion; best: EnrichedPlayer | null }) {
  const bp = champ.bestPlayer;
  const facePortrait = champ.podiumSkins?.find((skin) => skin.rank === 3)?.url ?? champ.icon;
  return (
    <div className="glass mb-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line px-3 py-3 sm:px-4">
      <Link href={`/champions/${champ.slug}`} className="group flex min-w-0 items-center gap-3 transition hover:opacity-90">
        <span className={`h-11 w-11 shrink-0 overflow-hidden rounded-full ${champ.isHard ? "ring-2 ring-bad/70" : "ring-1 ring-white/20"}`}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={facePortrait}
            alt=""
            width={44}
            height={44}
            className="h-full w-full object-cover"
            onError={(event) => {
              if (event.currentTarget.src !== champ.icon) event.currentTarget.src = champ.icon;
            }}
          />
        </span>
        <span className="min-w-0">
          <span className="block truncate text-base font-semibold leading-tight tracking-tight group-hover:text-accent sm:text-lg">{champ.name}</span>
          <span className="block truncate text-[0.65rem] uppercase tracking-[0.14em] text-muted">{champ.role} · {champ.class}</span>
        </span>
      </Link>
      <div className="flex flex-wrap items-center gap-2">
        <TierChip tier={champ.tier} />
        <span className="rounded-md border border-line bg-white/[0.04] px-2 py-0.5 text-xs font-semibold tabular-nums text-accent sm:text-sm">{champ.wr.toFixed(1)}% win rate</span>
      </div>
      {bp && (
        <div className="flex min-w-0 items-center gap-2 border-l border-line pl-3 sm:ml-auto sm:pl-4">
          <Glyph d={GLYPHS.crown} className="shrink-0 text-gold" size={16} />
          <span className="min-w-0">
            <span className="block text-[0.6rem] uppercase tracking-[0.16em] text-muted">Best this season</span>
            <span className="block max-w-[10rem] truncate text-sm font-semibold text-gold" title={bp.player}>{bp.player}</span>
          </span>
          {best?.tier && <TierBadge tier={best.tier} size={18} />}
        </div>
      )}
    </div>
  );
}

function PlayerPodium({
  podium,
  championName,
  championIcon,
  championIconLocal,
  podiumSkins,
}: {
  podium?: BestPlayerPodium | null;
  championName: string;
  championIcon?: string;
  /** `/champions/<slug>.png`, rehosted on our own origin. Preferred over
   *  `championIcon`, which is a game.gtimg.cn URL: Tencent's CDN is slow to
   *  reach from Europe and NA, and it is the podium's hero image, so it was
   *  the slowest thing on the page. The remote URL stays as the fallback. */
  championIconLocal?: string;
  podiumSkins?: { rank: number; name: string; tier: string; url: string; fallback?: string }[];
}) {
  // The button used to carry the explanation in a `title` alone, which is a
  // native tooltip: hover-only, so on a phone tapping it did nothing at all.
  const [scoringOpen, setScoringOpen] = useState(false);
  const players = podium?.players ?? [];
  if (!players.length) return null;
  // Name the servers the podium actually blends. It used to assert "EU, NA
  // and CN" unconditionally, which would have been a straight falsehood the
  // moment the global podium stopped requiring all three.
  const scopeLabel = podium?.scope === "global"
    ? `${(podium.servers ?? []).join(" and ") || "multiple servers"} normalized together`
    : `${podium?.server ?? "regional"} leaderboard`;
  // Keep first place in the visual centre, like a real podium. On narrow
  // screens the winner returns to the top of the reading order, while the
  // desktop layout uses the familiar 2–1–3 arrangement.
  const rankFor = (player: NonNullable<typeof players[number]>) => players.indexOf(player) + 1;
  const rankTone = (rank: number) => rank === 1
    ? "bg-gradient-to-b from-[#211b12]/98 via-[#10151f]/98 to-[#080d17]/98 shadow-[0_18px_70px_rgb(255_215_110/0.17)]"
    : rank === 2
      ? "bg-gradient-to-b from-[#101d32]/98 via-[#0a1425]/98 to-[#070e1a]/98 shadow-[0_12px_45px_rgb(91_178_255/0.12)]"
      : "bg-gradient-to-b from-[#291a19]/98 via-[#15131c]/98 to-[#0a0d16]/98 shadow-[0_12px_45px_rgb(221_133_88/0.12)]";
  const pedestalTone = (rank: number) => rank === 1
    ? "border-gold/55 bg-gradient-to-b from-[#6d5420]/80 to-[#1a150c]/95 text-gold shadow-[0_10px_35px_rgb(255_215_110/0.22)]"
    : rank === 2
      ? "border-sky-300/40 bg-gradient-to-b from-[#263e5e]/90 to-[#101a2b]/95 text-sky-100 shadow-[0_8px_30px_rgb(91_178_255/0.15)]"
      : "border-orange-300/40 bg-gradient-to-b from-[#593426]/90 to-[#1d1515]/95 text-orange-100 shadow-[0_8px_30px_rgb(221_133_88/0.14)]";
  const frameTone = (rank: number) => rank === 1
    ? "bg-[linear-gradient(135deg,#fff1a8_0%,#d39b2b_18%,#6f4d17_45%,#ffe58a_68%,#8d641d_100%)]"
    : rank === 2
      ? "bg-[linear-gradient(135deg,#d9f1ff_0%,#6fa8d8_18%,#294e78_48%,#c7e7ff_72%,#3f668e_100%)]"
      : "bg-[linear-gradient(135deg,#ffd8b8_0%,#bd7750_18%,#643727_48%,#edb18a_72%,#7b432f_100%)]";
  const rankLabel = (rank: number) => rank === 1 ? "CHAMPION" : `PLACE ${rank}`;
  return (
    <section className="podium-stage no-plate glass relative mb-5 overflow-hidden rounded-[1.5rem] border border-white/[0.11] shadow-[0_28px_90px_rgba(0,0,0,.3)]">
      <div className="hidden" aria-hidden>
      <div aria-hidden className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_24%,rgb(255_255_255/0.9)_0%,rgb(248_251_253/0.86)_20%,rgb(216_229_241/0.8)_48%,transparent_78%),linear-gradient(90deg,rgb(39_61_84/0.38),transparent_28%,transparent_72%,rgb(39_61_84/0.38)),linear-gradient(180deg,rgb(220_231_241/0.8),rgb(143_162_182/0.98)_100%)]" />
      {/* Stage lights: soft, angled cones with a brighter source at the ceiling. */}
      <div aria-hidden className="pointer-events-none absolute -top-8 left-[7%] h-[78%] w-[36%] origin-top -rotate-[17deg] bg-gradient-to-b from-white/52 via-white/24 to-transparent blur-xl" style={{ clipPath: "polygon(40% 0, 60% 0, 100% 100%, 0 100%)" }} />
      <div aria-hidden className="pointer-events-none absolute -top-8 right-[7%] h-[78%] w-[36%] origin-top rotate-[17deg] bg-gradient-to-b from-white/52 via-white/24 to-transparent blur-xl" style={{ clipPath: "polygon(40% 0, 60% 0, 100% 100%, 0 100%)" }} />
      <div aria-hidden className="pointer-events-none absolute -top-8 left-1/2 h-[84%] w-[35%] -translate-x-1/2 bg-gradient-to-b from-white/78 via-white/38 to-transparent blur-2xl" style={{ clipPath: "polygon(44% 0, 56% 0, 92% 100%, 8% 100%)" }} />
      <div aria-hidden className="absolute left-[23%] top-1 h-3 w-3 rounded-full bg-white shadow-[0_0_24px_8px_rgb(255_255_255/0.65)]" />
      <div aria-hidden className="absolute right-[23%] top-1 h-3 w-3 rounded-full bg-white shadow-[0_0_24px_8px_rgb(255_255_255/0.65)]" />
      <div aria-hidden className="absolute left-1/2 top-0 h-4 w-4 -translate-x-1/2 rounded-full bg-white shadow-[0_0_32px_12px_rgb(255_255_255/0.75)]" />
      <div aria-hidden className="pointer-events-none absolute inset-0 opacity-[0.13]" style={{ backgroundImage: "radial-gradient(rgb(50 83 116 / 0.3) 0.7px, transparent 0.7px), linear-gradient(115deg, transparent 0%, rgb(255 255 255 / 0.2) 48%, transparent 70%)", backgroundSize: "13px 13px, 100% 100%" }} />
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_35%,transparent_0%,transparent_43%,rgb(31_51_72/0.26)_100%)]" />
      <div aria-hidden className="pointer-events-none absolute left-1/2 top-[37%] h-[28%] w-[82%] -translate-x-1/2 rounded-[50%] bg-slate-700/14 blur-3xl" />
      {/* The back wall ends at a lit horizon; below it is a shallow
          perspective floor with restrained studio texture. */}
      <div aria-hidden className="absolute inset-x-0 bottom-[24%] h-px bg-gradient-to-r from-transparent via-slate-500/60 to-transparent shadow-[0_0_18px_rgb(116_160_196/0.45)]" />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-[-12%] bottom-[-18%] h-[44%] opacity-40"
        style={{
          background: "linear-gradient(180deg, rgba(246,250,253,0.42), rgba(176,196,216,0.2) 42%, rgba(84,108,133,0.18)), radial-gradient(rgb(54 87 119 / 0.22) 0.7px, transparent 0.7px), repeating-linear-gradient(90deg, rgba(68,113,155,0.12) 0 1px, transparent 1px 84px), repeating-linear-gradient(0deg, rgba(68,113,155,0.1) 0 1px, transparent 1px 38px)",
          backgroundSize: "100% 100%, 11px 11px, auto, auto",
          transform: "perspective(520px) rotateX(58deg)",
          transformOrigin: "bottom center",
        }}
      />
      <div aria-hidden className="pointer-events-none absolute bottom-[13%] left-1/2 h-12 w-[74%] -translate-x-1/2 rounded-[50%] bg-slate-700/25 blur-xl" />
      <div aria-hidden className="pointer-events-none absolute bottom-[17%] left-1/2 h-5 w-[45%] -translate-x-1/2 rounded-[50%] bg-slate-900/20 blur-md" />
      <div aria-hidden className="absolute inset-x-0 bottom-0 h-32 bg-[linear-gradient(180deg,transparent,rgb(87_108_130/0.28))]" />
      </div>

      <div className="relative flex flex-wrap items-center justify-between gap-4 px-5 pt-5 sm:px-7 sm:pt-6">
        <div className="rounded-xl border border-slate-700/70 bg-[#071427]/90 px-3 py-2 shadow-[0_10px_24px_rgb(12_29_53/0.25)] backdrop-blur-sm">
          {/* The wordmark is white, so it gets its own dark brand plate on the
              light studio wall instead of disappearing into the background. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="WrTrueMeta" width={210} height={30} className="block h-5 w-auto sm:h-7" />
        </div>
        <button
          type="button"
          onClick={() => setScoringOpen((open) => !open)}
          aria-expanded={scoringOpen}
          aria-controls="podium-scoring"
          className="rounded-full border border-accent/30 bg-accent/10 px-4 py-2 text-xs font-medium text-accent shadow-[0_0_22px_rgba(91,178,255,.1)] backdrop-blur transition hover:border-accent/50 hover:bg-accent/15"
        >
          How this is scored <span className="ml-1 inline-grid h-4 w-4 place-items-center rounded-full border border-sky-200/70 text-[0.65rem]">i</span>
        </button>
      </div>

      {scoringOpen && (
        <div
          id="podium-scoring"
          className="relative mx-5 mt-3 rounded-xl border border-slate-700/60 bg-[#071427]/90 px-4 py-3 text-xs leading-relaxed text-slate-200 backdrop-blur sm:mx-8"
        >
          <p>
            A current-season composite out of 100, not a raw win-rate race. Five
            parts, weighted:
          </p>
          <ul className="mt-2 space-y-1">
            <li><strong className="text-sky-200">Performance, 45%</strong> &mdash; win rate, confidence-adjusted so a short hot streak cannot outrank a long record.</li>
            <li><strong className="text-sky-200">Ladder, 20%</strong> &mdash; the player&apos;s ranked tier.</li>
            <li><strong className="text-sky-200">Board position, 20%</strong> &mdash; how high they sit on this champion&apos;s board.</li>
            <li><strong className="text-sky-200">Champion Score, 10%</strong> &mdash; mastery on the champion, compared within their own server.</li>
            <li><strong className="text-sky-200">Games, 5%</strong> &mdash; capped, so volume alone cannot win it.</li>
          </ul>
          <p className="mt-2 text-slate-400">
            A part we cannot read for a player is left out and the rest are
            reweighted, rather than scored as a zero.
          </p>
        </div>
      )}

      <div className="relative px-5 pb-6 pt-8 sm:px-7 sm:pb-8 sm:pt-10">
        <p className="text-[0.65rem] font-semibold uppercase tracking-[0.26em] text-gold">Top 3 this season</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-text sm:text-4xl">
          Best <span className="bg-gradient-to-r from-[#77aaff] via-[#8fbaff] to-[#74e1d0] bg-clip-text text-transparent">{championName}</span> players
        </h2>

        <div className="relative mx-auto mt-12 grid max-w-6xl grid-cols-3 items-end gap-2 sm:gap-8 sm:px-5 lg:gap-12 lg:px-12">
          {players.slice(0, 3).map((player) => {
            const rank = rankFor(player);
            const orderClass = rank === 1 ? "order-1 sm:order-2" : rank === 2 ? "order-2 sm:order-1" : "order-3";
            const portrait = podiumSkins?.find((skin) => skin.rank === rank);
            return (
              <article
                key={`${player.server ?? "?"}-${player.player}-${rank}`}
                aria-label={`${player.player}, ranked ${rank}`}
                className={`relative flex min-w-0 flex-col items-center text-center ${orderClass}`}
              >
                <Link
                  href={`/player?p=${encodeURIComponent(player.player)}`}
                  title={`Open ${player.player}'s player profile`}
                  className="group block w-full rounded-2xl focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 focus-visible:ring-offset-2"
                >
                <div className={`relative w-full rounded-2xl p-[2px] sm:p-[3px] shadow-[0_25px_32px_-14px_rgb(17_39_67/0.58)] transition group-hover:-translate-y-1 group-hover:shadow-[0_30px_38px_-14px_rgb(17_39_67/0.68)] ${rank === 1 ? "sm:shadow-[0_32px_42px_-16px_rgb(109_78_16/0.52)]" : ""} ${frameTone(rank)}`}>
                  <div className={`relative w-full rounded-[0.85rem] px-1.5 pb-3 pt-10 backdrop-blur-md sm:px-6 sm:pb-6 sm:pt-14 ${rankTone(rank)} ${rank === 1 ? "sm:pt-16" : ""}`}>
                    <div className={`absolute left-1/2 top-0 grid -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 bg-[#07101e] ${rank === 1 ? "h-16 w-16 border-gold shadow-[0_0_28px_rgb(255_215_110/0.42)] sm:h-28 sm:w-28 sm:shadow-[0_0_35px_rgb(255_215_110/0.42)]" : rank === 2 ? "h-14 w-14 border-sky-200/80 shadow-[0_0_20px_rgb(91_178_255/0.27)] sm:h-24 sm:w-24 sm:shadow-[0_0_24px_rgb(91_178_255/0.27)]" : "h-14 w-14 border-orange-200/75 shadow-[0_0_20px_rgb(221_133_88/0.23)] sm:h-20 sm:w-20 sm:shadow-[0_0_24px_rgb(221_133_88/0.23)]"}`}>
                    {rank === 1 && (
                      <>
                        <span aria-hidden className="pointer-events-none absolute -inset-2 rounded-full border-2 border-gold/80 shadow-[0_0_0_2px_rgb(255_215_110/0.14),0_0_20px_rgb(255_215_110/0.42)] sm:-inset-3 sm:shadow-[0_0_0_3px_rgb(255_215_110/0.14),0_0_28px_rgb(255_215_110/0.42)]" />
                        <span aria-hidden className="pointer-events-none absolute -inset-1 rounded-full border border-gold/35 sm:-inset-1.5" />
                      </>
                    )}
                    {portrait?.url || championIconLocal || championIcon ? (
                      <span
                        className="absolute inset-0 overflow-hidden rounded-full bg-cover bg-center"
                        /* The local champion icon sits UNDER the portrait as a
                           backdrop. Ranks 1 and 2 use communitydragon splash
                           tiles, which are remote and the slowest thing on the
                           page; until one arrives its circle was simply empty.
                           Painting the rehosted icon behind it means a face is
                           there immediately and the splash covers it when it
                           loads, so the wait stops being visible. */
                        style={championIconLocal && portrait?.url
                          ? { backgroundImage: `url(${championIconLocal})` }
                          : undefined}
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={portrait?.url || championIconLocal || championIcon}
                          alt={portrait?.name || championName}
                          title={portrait?.name}
                          width={96}
                          height={96}
                          fetchPriority={rank === 1 ? "high" : undefined}
                          decoding="async"
                          className="block w-full max-w-none rounded-full object-cover"
                          style={{
                            width: "100%",
                            height: "100%",
                            aspectRatio: "1 / 1",
                            objectFit: "cover",
                            // Skin splash tiles are face-forward but still
                            // leave more surrounding art than the base icon.
                            // Give only ranks 1–2 a little extra presence;
                            // the local base portrait stays at its natural fit.
                            transform: rank === 3 ? undefined : "scale(1.35)",
                            transformOrigin: "center",
                          }}
                          onError={(event) => {
                            const skinFallback = portrait?.fallback;
                            if (skinFallback && event.currentTarget.dataset.skinFallback !== "1") {
                              event.currentTarget.dataset.skinFallback = "1";
                              event.currentTarget.src = skinFallback;
                            } else if (championIcon && event.currentTarget.dataset.baseFallback !== "1") {
                              event.currentTarget.dataset.baseFallback = "1";
                              event.currentTarget.src = championIcon;
                            } else {
                              event.currentTarget.style.display = "none";
                            }
                          }}
                        />
                      </span>
                    ) : <Glyph d={GLYPHS.crown} size={rank === 1 ? 32 : 26} className="text-gold" />}
                    <span className={`absolute -bottom-2 grid h-7 w-7 place-items-center rounded-lg border text-xs font-black tabular-nums shadow-lg sm:-bottom-3 sm:h-9 sm:w-9 sm:text-base ${pedestalTone(rank)}`}>
                      {rank}
                    </span>
                    {rank === 1 && <Glyph d={GLYPHS.crown} size={22} className="absolute -top-7 text-gold drop-shadow-[0_0_8px_rgb(255_215_110/0.7)]" />}
                  </div>
                  <div className="flex min-h-5 items-center justify-center gap-2">
                    {player.server && <span className="rounded-full border border-white/15 bg-black/20 px-2 py-0.5 text-[0.65rem] font-semibold text-sky-100">{player.server}</span>}
                    {portrait?.tier && portrait.tier !== "base" && <span className="rounded-full border border-white/15 bg-black/20 px-2 py-0.5 text-[0.6rem] font-semibold uppercase tracking-wide text-slate-300">{portrait.tier}</span>}
                  </div>
                  <p className={`mt-2 truncate font-semibold ${rank === 1 ? "text-[0.75rem] text-white sm:text-2xl" : "text-[0.7rem] text-white sm:text-xl"}`} title={player.player}>{player.player}</p>
                  <div className="mt-2 flex min-h-5 flex-wrap justify-center gap-1 text-[0.5rem] text-slate-300 sm:min-h-6 sm:gap-1.5 sm:text-[0.7rem]">
                    {player.tier && <span className="rounded-md border border-white/15 bg-black/20 px-1 py-0.5 sm:px-2">{player.tier}</span>}
                    {player.championRank != null && <span className="rounded-md border border-white/15 bg-black/20 px-1 py-0.5 sm:px-2">board #{player.championRank}</span>}
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-x-1 gap-y-2 border-t border-white/15 pt-3 text-left sm:mt-5 sm:gap-x-3 sm:gap-y-3 sm:pt-4">
                    <div><p className="text-[0.5rem] text-slate-400 sm:text-xs">Score</p><strong className={`text-[0.9rem] tabular-nums sm:text-2xl ${rank === 1 ? "text-gold" : "text-white"}`}>{player.score != null ? player.score.toFixed(1) : "—"}</strong></div>
                    <div><p className="text-[0.5rem] text-slate-400 sm:text-xs">WR</p><strong className="text-[0.9rem] tabular-nums text-white sm:text-2xl">{player.winRate != null ? `${player.winRate.toFixed(1)}%` : "—"}</strong></div>
                    <div><p className="text-[0.5rem] text-slate-400 sm:text-xs">Games</p><strong className="text-[0.65rem] tabular-nums text-slate-100 sm:text-base">{player.games ?? "—"}</strong></div>
                    <div><p className="text-[0.5rem] text-slate-400 sm:text-xs">Champion score</p><strong className="text-[0.65rem] tabular-nums text-slate-100 sm:text-base">{player.championScore ?? "—"}</strong></div>
                  </div>
                  </div>
                </div>
                <div className={`flex w-full items-center justify-center rounded-t-xl border px-1 text-[0.42rem] font-black tracking-[0.12em] sm:px-3 sm:text-[0.7rem] sm:tracking-[0.25em] ${rank === 1 ? "h-20 sm:h-28" : rank === 2 ? "h-12 sm:h-16" : "h-7 sm:h-9"} ${pedestalTone(rank)}`}>
                  {rankLabel(rank)}
                </div>
                </Link>
              </article>
            );
          })}
        </div>
      </div>

      <p className="relative border-t border-white/[0.08] bg-black/15 px-5 py-3 text-[0.68rem] leading-relaxed text-faint sm:px-7">
        Current-season ranking · {scopeLabel} · scoring {podium?.scoringVersion ?? "best-player-v1"} · higher score means a stronger all-around season
      </p>
    </section>
  );
}

/* One ladder's worth of "emblem xN". The Ranked and Legendary Ranked queues
   each get their own, because they are separate ladders: a Legendary Master
   listed between Master and Grandmaster reads as one continuous ranking, and
   it is not one. */
function TierSpread({ label, rows }: { label: string; rows: [string, number][] }) {
  return (
    <div>
      <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">{label}</p>
      <div className="mt-1.5 flex items-center gap-2">
        {rows.map(([family, n]) => (
          <span key={family} className="inline-flex items-center gap-0.5 text-xs text-muted">
            <TierBadge tier={family} size={22} />
            ×{n}
          </span>
        ))}
      </div>
    </div>
  );
}

/* Runes and summoner spells render as art, like items: a rune page reads as
   a row of icons far faster than five names separated by dots.

   A name with no art is a name the build extractor invented -- the vision
   model substitutes League PC rune names when it cannot read an icon, and
   17 such names were confirmed as runes that do not exist in the game. Those
   are dropped rather than rendered, so the page never shows a rune nobody
   can equip. data/rune_extraction_report.txt tracks them for the rework. */
function ArtIcon({ src, name, size }: { src?: string; name: string; size: number }) {
  if (!src) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={name}
      title={name}
      width={size}
      height={size}
      loading="lazy"
      className="shrink-0 rounded-md bg-black/30 object-contain ring-1 ring-white/10"
      style={{ width: size, height: size }}
    />
  );
}

function ItemIcon({ slug, name, icons, size = 26, className = "" }: {
  slug: string | null; name: string; icons: Record<string, string>; size?: number;
  className?: string;
}) {
  const src = slug ? icons[slug] : undefined;
  if (!src) {
    return (
      <span
        title={name}
        className={`grid shrink-0 place-items-center rounded-md border border-line bg-white/5 text-[0.55rem] text-faint ${className}`}
        style={{ width: size, height: size }}
      >
        ?
      </span>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={name}
      title={name}
      width={size}
      height={size}
      loading="lazy"
      className={`shrink-0 rounded-md border border-line/70 bg-black/30 object-cover ${className}`}
      style={{ width: size, height: size }}
    />
  );
}

/* What the whole top 50 agrees on: item pick rates, tier spread, averages. */
function ChampionPulse({ payload, icons, runeIcons, spellIcons }: {
  payload: EnrichedPayload; icons: Record<string, string>;
  runeIcons: Record<string, string>; spellIcons: Record<string, string>;
}) {
  const pulse = useMemo(() => {
    const players = payload.players;
    const withBuild = players.filter((p) => p.build?.items?.length);
    const freq = new Map<string, { name: string; slug: string; n: number }>();
    for (const p of withBuild) {
      for (const it of p.build!.items) {
        if (!it.slug) continue;
        const cur = freq.get(it.slug) ?? { name: it.name, slug: it.slug, n: 0 };
        cur.n += 1;
        freq.set(it.slug, cur);
      }
    }
    const topItems = [...freq.values()].sort((a, b) => b.n - a.n).slice(0, 6);

    const tiers = new Map<string, number>();
    for (const p of players) {
      if (!p.tier) continue;
      // Group by the SAME family the badge draws. Taking the first word
      // collapsed the whole Legendary Ranked ladder -- Master, Grandmaster,
      // Challenger and Commander -- into one bucket called "Legendary",
      // which is four different tiers counted as one and drawn with no
      // emblem, since "legendary" alone owns no art.
      const { family } = tierParts(p.tier);
      tiers.set(family, (tiers.get(family) ?? 0) + 1);
    }
    // Two ladders, two rows. Legendary Ranked is a separate queue with its
    // own tiers, so a Legendary Master sitting between Master and Grandmaster
    // reads as if it were part of one ordered ladder, which it is not. Each
    // player holds exactly one tier, so the split partitions them cleanly.
    const byCount = (a: [string, number], b: [string, number]) => b[1] - a[1];
    const entries = [...tiers.entries()];
    const tierSpread = entries.filter(([f]) => !f.startsWith("legendary")).sort(byCount);
    const legendarySpread = entries.filter(([f]) => f.startsWith("legendary")).sort(byCount);

    const kdas = players.map((p) => p.stats?.ranked?.kda).filter((v): v is number => v != null);
    const avgKda = kdas.length ? kdas.reduce((a, b) => a + b, 0) / kdas.length : null;

    const keystones = new Map<string, number>();
    const spellPairs = new Map<string, number>();
    const cores = new Map<string, number>();
    for (const p of withBuild) {
      const ks = p.build!.runes?.[0];
      if (ks) keystones.set(ks, (keystones.get(ks) ?? 0) + 1);
      const spells = p.build!.spells;
      if (spells?.length) {
        const pair = [...spells].sort().join(" + ");
        spellPairs.set(pair, (spellPairs.get(pair) ?? 0) + 1);
      }
      const core = p.build!.items.map((i) => i.slug).filter(Boolean).sort().join("|");
      if (core.split("|").length >= 5) cores.set(core, (cores.get(core) ?? 0) + 1);
    }
    const topKeystone = [...keystones.entries()].sort((a, b) => b[1] - a[1])[0];
    const topSpells = [...spellPairs.entries()].sort((a, b) => b[1] - a[1])[0];
    const conformity = Math.max(0, ...cores.values());

    // Legendary tax: how much win rate the same players give up in the
    // sweatier queue (players with 10+ legendary games).
    const rankedWr = players.map((p) => p.stats?.ranked?.wr).filter((v): v is number => v != null);
    const legendWr = players
      .filter((p) => (p.stats?.legendary?.games ?? 0) >= 10)
      .map((p) => p.stats!.legendary!.wr)
      .filter((v): v is number => v != null);
    const mean = (a: number[]) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
    const mRanked = mean(rankedWr);
    const mLegend = mean(legendWr);
    const legendaryTax = mRanked != null && mLegend != null ? mLegend - mRanked : null;

    const fbRates = players
      .map((p) => p.stats?.ranked)
      .filter((r): r is QueueStats => r != null && (r.games ?? 0) > 0 && r.firstBlood != null)
      .map((r) => (r.firstBlood! / r.games!) * 100);
    const firstBlood = mean(fbRates);
    const pentas = players.reduce((acc, p) => acc + (p.stats?.ranked?.penta ?? 0), 0);

    return { topItems, tierSpread, legendarySpread, avgKda, topKeystone, topSpells, conformity,
             legendaryTax, firstBlood, pentas, nBuilds: withBuild.length };
  }, [payload]);

  if (!pulse.nBuilds) return null;
  return (
    <div className="glass mb-4 flex flex-wrap items-center gap-x-5 gap-y-3 rounded-2xl px-4 py-3.5 sm:gap-x-8 sm:px-5 sm:py-4">
      <div>
        <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">
          Core items across the board
        </p>
        <div className="mt-1.5 flex items-center gap-1.5">
          {pulse.topItems.map((it) => (
            <span key={it.slug} className="flex flex-col items-center gap-0.5">
              <ItemIcon slug={it.slug} name={it.name} icons={icons} size={30} />
              <span className="text-[0.6rem] tabular-nums text-faint">
                {Math.round((it.n / pulse.nBuilds) * 100)}%
              </span>
            </span>
          ))}
        </div>
      </div>
      {pulse.tierSpread.length > 0 && (
        <TierSpread label="Ranked tiers" rows={pulse.tierSpread} />
      )}
      {pulse.legendarySpread.length > 0 && (
        <TierSpread label="Legendary Ranked" rows={pulse.legendarySpread} />
      )}
      {pulse.avgKda != null && (
        <div>
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">Avg ranked KDA</p>
          <p className="mt-1.5 text-lg font-semibold text-accent">{pulse.avgKda.toFixed(1)}</p>
        </div>
      )}
      {pulse.topKeystone && (
        <div>
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">Top keystone</p>
          <p className="mt-1.5 flex items-center gap-1.5 text-sm font-medium">
            <ArtIcon src={runeIcons[pulse.topKeystone[0]]} name={pulse.topKeystone[0]} size={22} />
            {pulse.topKeystone[0]}
            <span className="text-xs text-faint">
              {Math.round((pulse.topKeystone[1] / pulse.nBuilds) * 100)}%
            </span>
          </p>
        </div>
      )}
      {pulse.topSpells && (
        <div>
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">Spells</p>
          <p className="mt-1.5 flex items-center gap-1.5 text-sm font-medium">
            {pulse.topSpells[0].split(" + ").map((sp) => (
              <ArtIcon key={sp} src={spellIcons[sp]} name={sp} size={22} />
            ))}
            <span className="text-xs text-faint">
              {Math.round((pulse.topSpells[1] / pulse.nBuilds) * 100)}%
            </span>
          </p>
        </div>
      )}
      {pulse.conformity >= 2 && (
        <div title="Players running the exact same item core">
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">Same core</p>
          <p className="mt-1.5 text-sm font-medium tabular-nums">
            {pulse.conformity}<span className="text-xs text-faint">/{pulse.nBuilds}</span>
          </p>
        </div>
      )}
      {pulse.legendaryTax != null && (
        <div title="Win rate change for these players in Legendary Ranked">
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">Legendary tax</p>
          <p className={`mt-1.5 text-sm font-semibold tabular-nums ${pulse.legendaryTax >= 0 ? "text-accent" : "text-bad"}`}>
            {pulse.legendaryTax >= 0 ? "+" : ""}{pulse.legendaryTax.toFixed(1)}pp
          </p>
        </div>
      )}
      {pulse.firstBlood != null && (
        <div title="Share of ranked games with first blood">
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">First blood</p>
          <p className="mt-1.5 text-sm font-medium tabular-nums">{pulse.firstBlood.toFixed(1)}%</p>
        </div>
      )}
      {pulse.pentas > 0 && (
        <div title="Pentakills across the board, ranked queue">
          <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">Pentakills</p>
          <p className="mt-1.5 text-sm font-semibold text-gold tabular-nums">{pulse.pentas}</p>
        </div>
      )}
    </div>
  );
}

function ExpandedRow({ p, icons, runeIcons, spellIcons }: {
  p: EnrichedPlayer;
  icons: Record<string, string>;
  runeIcons: Record<string, string>;
  spellIcons: Record<string, string>;
}) {
  const runes = (p.build?.runes ?? []).filter((r) => runeIcons[r]);
  const spells = (p.build?.spells ?? []).filter((s) => spellIcons[s]);
  // spans: rank, player, build, win rate, confidence, games, mastery, chevron
  return (
    <td colSpan={8} className="px-4 pb-4 pt-1">
      <div className="flex flex-col gap-3">
        {p.build && (
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <div className="flex items-center gap-1.5">
              {p.build.items.map((it, i) => (
                <ItemIcon key={`${it.slug}-${i}`} slug={it.slug} name={it.name} icons={icons} size={32} />
              ))}
            </div>
            {runes.length > 0 && (
              <span className="flex items-center gap-1.5" title={runes.join(" · ")}>
                {runes.map((r, i) => (
                  /* keystone first and larger: it is the page's identity */
                  <ArtIcon key={`${r}-${i}`} src={runeIcons[r]} name={r} size={i === 0 ? 30 : 24} />
                ))}
              </span>
            )}
            {spells.length > 0 && (
              <span className="flex items-center gap-1.5" title={spells.join(" + ")}>
                {spells.map((s, i) => (
                  <ArtIcon key={`${s}-${i}`} src={spellIcons[s]} name={s} size={24} />
                ))}
              </span>
            )}
          </div>
        )}
        <div className="grid gap-3 lg:grid-cols-2">
          {p.stats?.ranked && <QueuePanel title="Ranked" s={p.stats.ranked} />}
          {p.stats?.legendary && <QueuePanel title="Legendary Ranked" s={p.stats.legendary} />}
        </div>
        {!p.build && !p.stats && (
          <p className="text-sm text-faint">No detail captured for this player.</p>
        )}
      </div>
    </td>
  );
}

export function LeaderboardView({ champions, championsNa, itemIcons, runeIcons, spellIcons }: {
  champions: SlimChampion[];
  championsNa: SlimChampion[];
  itemIcons: Record<string, string>;
  runeIcons: Record<string, string>;
  spellIcons: Record<string, string>;
}) {
  const [region, setRegion] = useState<Region>("EU");
  // The champion list follows the region: NA covers fewer champions while its
  // collection runs, and picking one it has no board for would render an
  // empty table rather than an honest "not collected yet".
  const regionChampions = region === "NA" ? championsNa : champions;
  const byName = useMemo(
    () => [...regionChampions].sort((a, b) => a.name.localeCompare(b.name)),
    [regionChampions]
  );
  const [slug, setSlug] = useState(champions[0]?.slug ?? "");
  const [data, setData] = useState<Record<string, Row[]> | null>(null);
  const [enriched, setEnriched] = useState<EnrichedPayload | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("r");
  const [dir, setDir] = useState<"asc" | "desc">("asc");
  // one champion's enriched file is ~50 KB; keep what was already fetched
  const enrichedCache = useRef<Map<string, EnrichedPayload | null>>(new Map());

  // ?region=NA lands on NA. Runs after mount for the same reason the champion
  // param below does: the prerendered HTML must stay deterministic.
  useEffect(() => {
    const want = regionFromQuery(window.location.search, LEADERBOARD_REGIONS);
    if (want) setRegion(want);
  }, []);

  useEffect(() => {
    const param = new URLSearchParams(window.location.search).get("champion");
    if (param) {
      const norm = param.trim().toLowerCase();
      const match = champions.find(
        (c) => c.slug === norm || c.name.toLowerCase() === norm
      );
      if (match) setSlug(match.slug);
    }
  }, [champions]);

  // The thin table is published per server. Global and CN files are optional
  // until the player-level CN collection has completed; a missing file is
  // handled as an honest unavailable state below.
  useEffect(() => {
    let cancelled = false;
    setData(null);
    const playersPath = region === "NA" ? "/players-na.json" : region === "CN" ? "/players-cn.json" : region === "Global" ? "/players-global.json" : "/players.json";
    fetch(playersPath)
      .then((r) => r.json())
      .then((payload) => { if (!cancelled) setData(payload); })
      .catch(() => { if (!cancelled) setData({}); });
    return () => { cancelled = true; };
  }, [region]);

  useEffect(() => {
    // The global file is ordered by the composite score, while regional
    // boards use the Wilson confidence score. Resetting the sort on a view
    // change prevents a stale regional key from silently reordering Global.
    setSortKey("r");
    setDir("asc");
  }, [region]);

  // The per-champion enriched file exists only once that champion has been
  // recaptured with the extended pipeline; 404 simply means the thin table.
  useEffect(() => {
    setExpanded(null);
    const cached = enrichedCache.current.get(`${region}:${slug}`);
    if (cached !== undefined) {
      setEnriched(cached);
      return;
    }
    let cancelled = false;
    setEnriched(null);
    const detailPath = region === "NA" ? `/players/na/${slug}.json` : region === "CN" ? `/players/cn/${slug}.json` : region === "Global" ? `/players/global/${slug}.json` : `/players/${slug}.json`;
    fetch(detailPath)
      .then((r) => (r.ok ? r.json() : null))
      .then((payload: EnrichedPayload | null) => {
        enrichedCache.current.set(`${region}:${slug}`, payload);
        if (!cancelled) setEnriched(payload);
      })
      .catch(() => {
        enrichedCache.current.set(`${region}:${slug}`, null);
        if (!cancelled) setEnriched(null);
      });
    return () => {
      cancelled = true;
    };
  }, [slug, region]);

  // A champion selected on EU may not exist on NA yet; fall back to the
  // region's first champion rather than showing an empty table.
  useEffect(() => {
    if (regionChampions.length && !regionChampions.some((c) => c.slug === slug)) {
      setSlug(regionChampions[0].slug);
    }
  }, [regionChampions, slug]);

  const champ = regionChampions.find((c) => c.slug === slug);
  const rows: (Row | EnrichedPlayer)[] = useMemo(() => {
    // The composite score `b` is produced by the SCORING pass that writes the
    // region-wide players file; the enriched per-champion file is a capture
    // artifact and has never carried it. Since the enriched file wins here,
    // every champion that has one showed an empty "Best score" column -- on
    // EU as well as NA. Rather than duplicate the score into the capture
    // export, carry it across by rank, which keeps one source of truth for it.
    const scoreByRank = new Map<number, number>();
    for (const row of data?.[slug] ?? []) {
      if (row.r != null && row.b != null) scoreByRank.set(row.r, row.b);
    }
    const base: (Row | EnrichedPlayer)[] = enriched?.players
      ? enriched.players.map((row) =>
          row.b == null && row.r != null && scoreByRank.has(row.r)
            ? { ...row, b: scoreByRank.get(row.r) }
            : row,
        )
      : data?.[slug] ?? [];
    // Derived sort keys return null when the row cannot supply them, which
    // `num` sorts last in either direction.
    const key = (row: Row | EnrichedPlayer) => {
      if (sortKey === "wilson") return wilsonScore(row.w, row.g);
      if (sortKey === "composite") return row.b ?? null;
      if (sortKey === "tier") return tierRank((row as EnrichedPlayer).tier);
      return row[sortKey];
    };
    return [...base].sort((a, b) => {
      const cmp = num(key(a)) - num(key(b));
      // Ties on the sort key fall back to rank, so the order is stable and
      // reads sensibly instead of depending on the source array.
      return (dir === "asc" ? cmp : -cmp) || a.r - b.r;
    });
  }, [data, enriched, slug, sortKey, dir]);
  const hasDetail = enriched != null && enriched.players.length > 0;

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setDir(key === "r" ? "asc" : "desc");
    }
  };

  return (
    <div className="leaderboard-view">
      {/* Global and CN become fully populated after the player-level CN
          collection; keeping them visible now makes the rollout state clear. */}
      <div className="glass mb-5 grid gap-3 rounded-[1.4rem] border border-white/[0.1] p-3 shadow-[inset_0_1px_rgba(255,255,255,.09)] sm:p-4 lg:grid-cols-[1fr_22rem] lg:items-end">
        <div>
          <p className="mb-2 text-[0.62rem] font-bold uppercase tracking-[0.16em] text-faint">Region</p>
          <RegionToggle region={region} onChange={setRegion} regions={LEADERBOARD_REGIONS} />
        </div>
        {regionChampions.length > 0 && (
          <div>
            <p className="mb-2 text-[0.62rem] font-bold uppercase tracking-[0.16em] text-faint">Champion</p>
            <ChampionCombobox
              champions={byName.map((c) => ({ name: c.name, slug: c.slug, icon: c.icon }))}
              placeholder="Search a champion…"
              onSelect={(s) => setSlug(s)}
            />
          </div>
        )}
      </div>

      {regionChampions.length === 0 ? (
        <RegionComingSoon region={region} />
      ) : (
      <>
      {champ && (
        <ChampionContextBar
          champ={region === "Global" || region === "CN" ? { ...champ, bestPlayer: null } : champ}
          best={region === "Global" || region === "CN" ? null : matchBestPlayer(champ, enriched)}
        />
      )}

      {champ && (
        <PlayerPodium
          podium={region === "Global" ? champ.globalBestPlayerPodium : region === "CN" ? null : champ.bestPlayerPodium}
          championName={champ.name}
          championIcon={champ.icon}
          championIconLocal={`/champions/${champ.slug}.png`}
          podiumSkins={champ.podiumSkins}
        />
      )}

      {/* The hand-recorded build for this champion's best player, when one has
          been entered in the admin console. Silent when it has not. */}
      <BestPlayerBuild slug={slug} championName={champ?.name} />

      {/* What the whole top 50 agrees on, from the freshly captured data */}
      {hasDetail && <ChampionPulse payload={enriched} icons={itemIcons} runeIcons={runeIcons} spellIcons={spellIcons} />}

      {/* What the Best column means, said where everyone can read it. The
          column header carries the same text as a title attribute, but a
          tooltip needs a hover and most of this page's readers are on a
          phone. An expandable pill puts the one unfamiliar column a tap away
          from its explanation. */}
      <details className="group mb-3 inline-block">
        <summary className="glass glass-hover inline-flex cursor-pointer list-none items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-medium text-muted">
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-accent/20 text-[0.65rem] font-bold text-accent">?</span>
          What does &ldquo;Best&rdquo; mean?
        </summary>
        <p className="mt-2 max-w-xl rounded-xl border border-line bg-black/30 p-3 text-xs leading-relaxed text-muted">
          <span className="font-semibold text-text">A current-season composite, not a raw win-rate race.</span>{" "}
          It combines confidence-adjusted win rate (45%), ladder strength (20%), champion-board
          position (20%), Champion Score (10%) and capped games experience (5%). Small samples
          and pure grinding cannot decide the podium by themselves.
        </p>
      </details>

      {/* Player table */}
      {data === null && !hasDetail ? (
        <div className="glass rounded-2xl p-10 text-center text-muted">Loading players…</div>
      ) : rows.length === 0 ? (
        <div className="glass rounded-2xl p-10 text-center text-muted">
          {region === "Global"
            ? "The global podium will appear after EU, NA and CN player-level collections are complete."
            : region === "CN"
              ? "CN player-level data will appear after the next collection finishes."
              : "No player data for this champion yet."}
        </div>
      ) : (
        <div className="glass overflow-x-auto rounded-2xl">
          <p className="border-b border-line px-3 py-2 text-[0.65rem] text-faint sm:hidden">
            Swipe horizontally to see Best score, Games and Mastery →
          </p>
          <table className="w-full min-w-[650px] border-collapse text-sm sm:min-w-[760px]">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
                <Th onClick={() => toggleSort("r")} active={sortKey === "r"} dir={dir} className="w-10 text-center sm:w-16">
                  <span
                    title="Position in the current sort. The smaller number below it, when shown, is the player's rank on the in-game leaderboard."
                    className="hidden sm:inline"
                  >
                    Rank
                  </span>
                  <span className="sm:hidden">#</span>
                </Th>
                <Th onClick={() => toggleSort("tier")} active={sortKey === "tier"} dir={dir}>
                  <span title="Sort by ranked tier. Legendary Ranked tiers sort above the standard ladder, since that queue is entered from the top of it.">
                    Player
                  </span>
                </Th>
                {hasDetail && <Th>Build</Th>}
                <Th onClick={() => toggleSort("w")} active={sortKey === "w"} dir={dir} right>
                  <span className="hidden sm:inline">Win rate</span>
                  <span className="sm:hidden">WR</span>
                </Th>
                <Th onClick={() => toggleSort("composite")} active={sortKey === "composite"} dir={dir} right>
                  <span title="Composite current-season score: confidence-adjusted win rate, ladder strength, champion-board position, Champion Score and capped games experience.">
                    Best score
                  </span>
                </Th>
                <Th onClick={() => toggleSort("g")} active={sortKey === "g"} dir={dir} right>
                  Games
                </Th>
                <Th onClick={() => toggleSort("s")} active={sortKey === "s"} dir={dir} right>
                  Mastery
                </Th>
                {hasDetail && <Th className="w-6 sm:w-10"> </Th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const e = hasDetail ? (row as EnrichedPlayer) : null;
                const open = e != null && expanded === row.r;
                const clickable = e != null && (e.build != null || e.stats != null);
                return (
                  <FragmentRow key={`${row.r}-${i}`}>
                    <tr
                      onClick={clickable ? () => setExpanded(open ? null : row.r) : undefined}
                      className={`border-b border-line/60 transition last:border-0 hover:bg-white/[0.03] ${clickable ? "cursor-pointer" : ""} ${open ? "bg-white/[0.03]" : ""}`}
                    >
                      {/* Position in the CURRENT ordering, always 1..N. It used
                          to show the in-game rank, which reads as scrambled the
                          moment you sort by anything else: "24, 1, 38, 2" is
                          correct and looks broken.

                          The board rank is still a real fact, so it sits under
                          the position whenever the two differ. Sorted by rank
                          they agree and the second line is not drawn -- except
                          where a snap-back duplicate was dropped, which leaves
                          a genuine gap in the board and is worth seeing. */}
                      <td className="px-1.5 py-2.5 text-center sm:px-3">
                        <span className={i < 3 ? "font-bold text-accent" : "text-faint"}>
                          {i + 1}
                        </span>
                        {row.r !== i + 1 && (
                          <span
                            className="block text-[0.6rem] leading-tight text-faint"
                            title={`Rank ${row.r} on the in-game leaderboard`}
                          >
                            #{row.r}
                          </span>
                        )}
                      </td>
                      <td className="max-w-[98px] px-1.5 py-2.5 sm:max-w-[240px] sm:px-3">
                        <span
                          className={`block truncate font-medium ${e?.hidden ? "italic text-faint" : ""}`}
                          title={e?.hidden
                            ? "This account advertises a boosting service. Its name is hidden and its games are excluded from champion win rates and records."
                            : undefined}
                        >
                          {row.p}
                        </span>
                        {row.v && <span className="mt-0.5 block text-[0.6rem] font-semibold uppercase tracking-wide text-faint">{row.v}</span>}
                        {(e?.tier || e?.banned) && (
                          <span className="mt-0.5 flex flex-wrap items-center gap-1">
                            {e?.tier && <TierBadge tier={e.tier} />}
                            {e?.banned && (
                              <span
                                title="This account has been permanently banned. Its row is shown as the game showed it, but its games are excluded from champion win rates and records."
                                className="rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-bad ring-1 ring-bad/40"
                              >
                                Permabanned
                              </span>
                            )}
                          </span>
                        )}
                      </td>
                      {hasDetail && (
                        <td className="min-w-[170px] px-1.5 py-2.5 sm:min-w-0 sm:px-3">
                          {e?.build ? (
                            <span className="flex items-center gap-0.5 sm:gap-1">
                              {e.build.items.slice(0, 6).map((it, j) => (
                                <ItemIcon
                                  key={`${it.slug}-${j}`}
                                  slug={it.slug}
                                  name={it.name}
                                  icons={itemIcons}
                                  size={22}
                                  className={j >= 4 ? "hidden sm:block" : ""}
                                />
                              ))}
                            </span>
                          ) : (
                            <span className="text-xs text-faint">-</span>
                          )}
                        </td>
                      )}
                      <td className="px-1.5 py-2.5 text-right font-semibold text-accent sm:px-3">
                        {row.w != null ? (
                          `${row.w.toFixed(1)}%`
                        ) : (
                          // The rank was captured but its win rate never read.
                          // A bare dash reads as "this player has no games";
                          // this says the number is missing, not zero, and it
                          // is what makes the row worth showing at all.
                          <span
                            title="The win rate for this rank could not be read from the capture. The player and their rank are correct; the number needs filling in by hand."
                            className="cursor-help font-normal text-faint"
                          >
                            not read
                          </span>
                        )}
                      </td>
                      <td className="px-1.5 py-2.5 text-right text-muted sm:px-3">
                        {(() => {
                          const composite = row.b;
                          return composite != null ? (
                            <span title="Composite current-season Best Player score">
                              {composite.toFixed(1)}
                            </span>
                          ) : "-";
                        })()}
                      </td>
                      <td className="px-1.5 py-2.5 text-right text-muted sm:px-3">
                        {row.g != null ? row.g.toLocaleString() : "-"}
                      </td>
                      <td className="px-1.5 py-2.5 text-right text-muted sm:px-3">
                        {row.s != null ? row.s.toLocaleString() : "-"}
                      </td>
                      {hasDetail && (
                        <td className="px-2 py-2.5 text-center text-faint">
                          {clickable ? (open ? "▾" : "▸") : ""}
                        </td>
                      )}
                    </tr>
                    {open && e && (
                      <tr className="border-b border-line/60 last:border-0">
                        <ExpandedRow p={e} icons={itemIcons} runeIcons={runeIcons} spellIcons={spellIcons} />
                      </tr>
                    )}
                  </FragmentRow>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {hasDetail && (
        <p className="mt-2 text-xs text-faint">
          Click a player row for their full build, runes and per-queue stats. Captured {enriched.capturedAt}.
        </p>
      )}
      </>
      )}
    </div>
  );
}

/* React fragments cannot carry keys through .map inside <tbody> without a
   wrapper; this keeps the expanded row adjacent to its player row. */
function FragmentRow({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

function Th({
  children,
  onClick,
  active,
  dir,
  right,
  className = "",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  active?: boolean;
  dir?: "asc" | "desc";
  right?: boolean;
  className?: string;
}) {
  const base = `px-1.5 py-3 font-semibold sm:px-3 ${right ? "text-right" : "text-left"} ${className}`;
  if (!onClick) return <th className={base}>{children}</th>;
  return (
    <th className={base}>
      <button
        onClick={onClick}
        className={`inline-flex items-center gap-1 transition hover:text-text ${active ? "text-accent" : ""} ${right ? "flex-row-reverse" : ""}`}
      >
        {children}
        {active && <span className="text-[0.6rem]">{dir === "asc" ? "▲" : "▼"}</span>}
      </button>
    </th>
  );
}
