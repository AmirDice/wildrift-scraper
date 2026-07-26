import type { Metadata } from "next";
import Link from "next/link";
import { Container, Card, ChampionAvatar } from "@/components/ui";
import { getChampions, site, type Champion } from "@/lib/data";
import {
  getChampionChangeRanking,
  getMostAdjustedChampions,
  getNeverChangedChampions,
} from "@/lib/champion-change-ranking";
import { daysSinceRelease, releaseDateLabel } from "@/lib/champion-releases";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";
import { CURRENT_PATCH } from "@/lib/patch";

export const metadata: Metadata = {
  title: `Wild Rift Balance Report Patch ${CURRENT_PATCH} | Most and Least Changed Champions`,
  description:
    "One page of Wild Rift balance history: the champions Riot changes most, the ones left alone longest, and the champion that has never received a single balance change.",
  alternates: { canonical: "/changes-report" },
};

/**
 * Built to be screenshotted, so it is built to fit: one screen, top fives, no
 * scrolling to reach the point.
 *
 * Everything here counts STANDARD balance changes only. The patch notes also
 * carry mode-only tuning (ARAM damage multipliers and the like), and mixing
 * those in rewards a champion who was never touched in the game most people
 * play. The two numbers disagree enough to matter: Miss Fortune has 21 standard
 * changes and 26 patch-note appearances.
 */
const TOP_N = 5;

export default function ChangesReportPage() {
  const champions = getChampions();

  const adjustments = getMostAdjustedChampions(champions);
  const mostAdjusted = adjustments.slice(0, TOP_N);
  const favorite = mostAdjusted[0];

  const neverChanged = getNeverChangedChampions(champions);
  const forgotten = neverChanged.find((champion) => champion.name === "Vel'Koz") ?? neverChanged[0];

  const longestUnchanged = getChampionChangeRanking(champions)
    .filter((entry) => entry.daysSinceBalanceChange != null && entry.champion.name !== forgotten?.name)
    .slice(0, TOP_N);

  const totalStandard = adjustments.reduce((sum, entry) => sum + entry.balanceChanges, 0);

  return (
    <Container className="py-8 sm:py-10">
      <header className="text-center">
        <p className="text-[0.7rem] font-semibold uppercase tracking-[0.2em] text-accent">
          WrTrueMeta · Wild Rift balance report · Patch {CURRENT_PATCH}
        </p>
        <h1 className="mx-auto mt-2 max-w-3xl text-2xl font-semibold leading-tight tracking-tight sm:text-4xl">
          {favorite && (
            <>
              Riot has changed {favorite.champion.name}{" "}
              <span className="text-bad">{favorite.balanceChanges} times</span>.{" "}
            </>
          )}
          {forgotten && (
            <>
              {forgotten.name} has never been changed <span className="text-gold">once</span>.
            </>
          )}
        </h1>
        <p className="mx-auto mt-2 max-w-2xl text-sm text-muted">
          Every standard balance change in the official patch notes, counted across {champions.length}{" "}
          champions and {totalStandard.toLocaleString()} changes. Mode-only tuning excluded.
        </p>
      </header>

      {/* The two extremes, as matching hero panels */}
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        {favorite && (
          <HeroPanel
            champion={favorite.champion}
            eyebrow="Riot's favorite"
            accent="text-bad"
            border="border-bad/25"
            value={String(favorite.balanceChanges)}
            valueClass="text-bad"
            caption="balance changes"
            body={
              <>
                No champion has been rebalanced more. Buffed, nerfed and re-tuned across{" "}
                {favorite.balanceChanges} separate patches
                {favorite.lastBalancePatch ? `, most recently in ${favorite.lastBalancePatch}` : ""}.
              </>
            }
          />
        )}
        {forgotten && <ForgottenPanel champion={forgotten} others={neverChanged.filter((c) => c.name !== forgotten.name)} />}
      </div>

      {/* Top fives */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="font-semibold">Riot&rsquo;s favorites</h2>
            <span className="text-[0.7rem] text-faint">balance changes</span>
          </div>
          <ol className="mt-2">
            {mostAdjusted.map((entry, index) => (
              <Row
                key={entry.champion.slug}
                index={index}
                champion={entry.champion}
                sub={entry.lastBalancePatch ? `Last changed in ${entry.lastBalancePatch}` : "No standard change recorded"}
                metric={`${entry.balanceChanges}`}
                metricClass="text-bad"
              />
            ))}
          </ol>
        </Card>

        <Card className="p-4">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="font-semibold">Left alone the longest</h2>
            <span className="text-[0.7rem] text-faint">since last change</span>
          </div>
          <ol className="mt-2">
            {longestUnchanged.map((entry, index) => (
              <Row
                key={entry.champion.slug}
                index={index}
                champion={entry.champion}
                sub={entry.lastBalancePatch ? `Last changed in patch ${entry.lastBalancePatch}` : "No standard change recorded"}
                metric={`${entry.daysSinceBalanceChange!.toLocaleString()}d`}
                metricClass="text-gold"
              />
            ))}
          </ol>
        </Card>
      </div>

      {/* Feature highlight, deliberately inside the screenshot frame */}
      <Link
        href={BUILD_TOOLS_LIVE ? "/build?tab=generate" : "/meta"}
        className="glass glass-hover mt-4 flex flex-col gap-2 rounded-2xl border border-line p-4 sm:flex-row sm:items-center sm:gap-5"
      >
        <span className="shrink-0 rounded-md bg-white/[0.06] px-2 py-1 text-[0.6rem] font-semibold uppercase tracking-wide text-muted">
          Also available
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-text">
            {BUILD_TOOLS_LIVE ? "Build generation & matchup planning" : "The whole patch in charts"}
          </span>
          <span className="mt-0.5 block text-xs text-muted">
            {BUILD_TOOLS_LIVE
              ? "Create a build around a champion and playstyle, or adjust it for the enemy team."
              : "Tier splits, win rate by class and role, and a win-rate-vs-popularity map of every champion."}
          </span>
        </span>
        <span className="shrink-0 text-xs font-medium text-faint">View →</span>
      </Link>

      <p className="mt-3 text-center text-[0.65rem] leading-relaxed text-faint">
        Source: official Wild Rift patch notes through patch {CURRENT_PATCH}. Standard balance changes only;
        mode-only tuning excluded. Full per-champion history at wrtruemeta.com/champion-changes
        {site.collectedOn ? ` · Win rates collected ${site.collectedOn}` : ""}
      </p>
    </Container>
  );
}

function Row({
  index, champion, sub, metric, metricClass,
}: {
  index: number; champion: Champion; sub: string; metric: string; metricClass: string;
}) {
  return (
    <li className="flex items-center gap-2.5 border-t border-line/60 py-1.5 first:border-t-0">
      <span className="w-4 text-center text-xs font-semibold text-faint">{index + 1}</span>
      <ChampionAvatar champion={champion} size={30} showBadges={false} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium leading-tight">{champion.name}</p>
        <p className="truncate text-[0.68rem] leading-tight text-muted">{sub}</p>
      </div>
      <span className={`shrink-0 text-sm font-semibold ${metricClass}`}>{metric}</span>
    </li>
  );
}

/** Shared shape for the two hero panels, so they read as a matched pair. */
function HeroPanel({
  champion, eyebrow, accent, border, value, valueClass, caption, body,
}: {
  champion: Champion;
  eyebrow: string;
  accent: string;
  border: string;
  value: string;
  valueClass: string;
  caption: string;
  body: React.ReactNode;
}) {
  return (
    <div className={`relative overflow-hidden rounded-2xl border ${border}`}>
      {champion.splash && (
        <>
          <div
            aria-hidden
            className="absolute inset-0 bg-cover"
            style={{ backgroundImage: `url(${champion.splash})`, backgroundPosition: "70% 26%" }}
          />
          <div aria-hidden className="absolute inset-0 bg-gradient-to-r from-bg via-bg/90 to-bg/45" />
        </>
      )}
      <div className="relative flex items-center gap-4 p-4 sm:p-5">
        <ChampionAvatar champion={champion} size={60} showBadges={false} />
        <div className="min-w-0 flex-1">
          <p className={`text-[0.65rem] font-semibold uppercase tracking-[0.16em] ${accent}`}>{eyebrow}</p>
          <h2 className="mt-0.5 text-2xl font-semibold tracking-tight">{champion.name}</h2>
          <p className="mt-1 text-xs leading-relaxed text-muted">{body}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className={`text-4xl font-semibold sm:text-5xl ${valueClass}`}>{value}</p>
          <p className="text-[0.6rem] font-semibold uppercase tracking-wide text-faint">{caption}</p>
        </div>
      </div>
    </div>
  );
}

function ForgottenPanel({ champion, others }: { champion: Champion; others: Champion[] }) {
  const days = daysSinceRelease(champion.name);
  const released = releaseDateLabel(champion.name);

  return (
    <HeroPanel
      champion={champion}
      eyebrow="The forgotten champion"
      accent="text-gold"
      border="border-gold/25"
      value="0"
      valueClass="text-gold"
      caption="changes, ever"
      body={
        <>
          {released && days != null ? (
            <>
              Released {released} and untouched for all {days.toLocaleString()} days since. Not a buff, not a
              nerf, not once.
            </>
          ) : (
            <>Not one balance change in the entire period we have patch notes for. Not a buff, not a nerf.</>
          )}
          {others.length > 0 && ` ${others.map((entry) => entry.name).join(", ")} ${others.length === 1 ? "is" : "are"} the only other untouched ${others.length === 1 ? "name" : "names"}.`}
        </>
      }
    />
  );
}
