import type { Metadata } from "next";
import Link from "next/link";
import { Container } from "@/components/ui";
import { getChampion } from "@/lib/data";
import { topWinners, topLosers, MOVERS_META, type Mover } from "@/lib/movers";
import { moverWhy } from "@/lib/movers-why";
import { NextStep } from "@/components/next-step";
import { AdSlot } from "@/components/ad-slot";

/* eslint-disable @next/next/no-img-element */

/**
 * The full movers board: every champion whose China win rate moved between
 * the last two collections, risers and fallers side by side.
 *
 * This page exists because the home-page highlight shows five of each and
 * has to link SOMEWHERE for the rest. That used to be the season recap;
 * when the recap was retired (2026-08-16) the movers lost their only full
 * listing, and pointing the highlight at the Balance Report answered a
 * different question -- patch-note changes are what Riot did, movers are
 * what the ladder did about it.
 */

const PATCH = MOVERS_META.patch;

export const metadata: Metadata = {
  title: `Wild Rift Biggest Winners & Losers | Patch ${PATCH} Movers`,
  description:
    `Every Wild Rift champion whose China win rate has moved since patch ${PATCH} went live: the biggest risers and fallers at ${MOVERS_META.scope}, updated daily.`,
  alternates: { canonical: "/movers" },
};

const dateLabel = (raw: string) => {
  // cn_movers stamps collections as yyyymmdd.
  const m = /^(\d{4})(\d{2})(\d{2})$/.exec(raw);
  const d = m ? new Date(`${m[1]}-${m[2]}-${m[3]}T00:00:00Z`) : new Date(raw);
  return Number.isNaN(d.getTime())
    ? raw
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
};

export default function MoversPage() {
  // Everything that moved, not just the highlight's five: the pick-rate floor
  // stays, because a 4-point swing on a champion nobody plays is noise.
  const winners = topWinners(60);
  const losers = topLosers(60);

  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
        Biggest Winners &amp; Losers
        {PATCH && <span className="text-muted"> · Patch {PATCH}</span>}
      </h1>
      {MOVERS_META.measuresPatch ? (
        <p className="mt-2 max-w-2xl text-muted">
          {`Every champion whose China win rate has moved since the last collection before patch ${PATCH} `
            + `(${dateLabel(MOVERS_META.before)} to ${dateLabel(MOVERS_META.after)}, `
            + `${MOVERS_META.postPatchDays} ${MOVERS_META.postPatchDays === 1 ? "day" : "days"} of games on ${PATCH}), `
            + `measured at ${MOVERS_META.scope}. Movement is the ladder's verdict on the patch: what actually got `
            + `stronger or weaker in real games, not what the patch notes intended.`}
          {MOVERS_META.postPatchDays < 3 && " With this few days of games, treat small moves as noise."}
        </p>
      ) : (
        <div className="mt-4 max-w-2xl rounded-2xl border border-accent/25 bg-accent/[0.05] p-5">
          <p className="text-sm font-semibold text-text">{`Waiting for the first day of ${PATCH} games in China.`}</p>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            {`Patch ${PATCH} went live on ${dateLabel(MOVERS_META.patchLive)}. China's win rates are published `
              + `a day behind, and the newest collection (${dateLabel(MOVERS_META.after)}) still predates the `
              + `patch. Showing it now would present a week of pre-patch drift as the patch's verdict, so the `
              + `winners and losers appear here once the first day of ${PATCH} games is in, and grow more `
              + `reliable each day after.`}
          </p>
        </div>
      )}

      <AdSlot placement="inline" bare className="my-6" />
      {MOVERS_META.measuresPatch && (
        <div className="mt-8 grid gap-5 lg:grid-cols-2">
          <MoverColumn title="Biggest Winners" accent="#22c55e" up movers={winners} />
          <MoverColumn title="Biggest Losers" accent="#ef4444" movers={losers} />
        </div>
      )}

      <p className="mt-6 text-xs leading-relaxed text-faint">
        Source: official China server data (lolm.qq.com). Champions below a 0.5% pick
        rate are excluded so one-trick swings don&rsquo;t read as meta movement. Under each
        name: whether the patch changed that champion, and any item the patch changed that
        is in one of its commonly built China cores, since an item change moves every
        champion that builds it. For what
        the patch notes themselves changed, see the{" "}
        <Link href="/changes-report" className="font-semibold text-accent transition hover:opacity-80">
          Balance Report
        </Link>.
      </p>
      <NextStep steps={["build", "counter", "meta"]} />
    </Container>
  );
}

function MoverColumn({ title, accent, movers, up = false }: {
  title: string; accent: string; movers: Mover[]; up?: boolean;
}) {
  return (
    <div className="glass rounded-2xl p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="grid h-7 w-7 place-items-center rounded-md text-base font-black"
              style={{ background: `${accent}22`, color: accent }}>
          {up ? "▲" : "▼"}
        </span>
        <h2 className="text-base font-bold">{title}</h2>
        <span className="ml-auto text-xs text-faint">{movers.length} champions</span>
      </div>
      <div className="flex flex-col gap-1">
        {movers.map((m, i) => {
          const champ = getChampion(m.slug);
          const why = moverWhy(m.slug, m.name);
          return (
            <Link key={m.slug} href={`/champions/${m.slug}`}
                  className="flex items-center gap-2.5 rounded-lg px-1.5 py-1 transition hover:bg-white/[0.05]">
              <span className="w-6 shrink-0 text-right text-xs font-bold text-faint">{i + 1}</span>
              {champ ? (
                <img src={champ.icon} alt="" width={30} height={30} className="shrink-0 rounded-full ring-1 ring-white/10" />
              ) : (
                <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-full bg-white/10 text-[0.55rem] font-bold text-faint">
                  {m.name.slice(0, 2)}
                </span>
              )}
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{m.name}</span>
                {(why.changed || why.items.length > 0) && (
                  <span className="block truncate text-[0.65rem] text-faint">
                    {[why.changed ? `changed in ${PATCH}` : "", why.items.length ? `builds ${why.items.join(", ")}` : ""]
                      .filter(Boolean).join(" · ")}
                  </span>
                )}
              </span>
              <span className="hidden shrink-0 text-xs text-faint sm:inline">pick {m.pickRate.toFixed(1)}%</span>
              <span className="shrink-0 text-xs text-muted">
                {m.oldWr.toFixed(1)}<span className="text-faint"> → </span>
                <span className="font-semibold text-text">{m.newWr.toFixed(1)}%</span>
              </span>
              <span className="w-12 shrink-0 text-right text-sm font-black" style={{ color: accent }}>
                {m.delta > 0 ? "+" : ""}{m.delta}
              </span>
            </Link>
          );
        })}
        {movers.length === 0 && (
          <p className="px-1.5 py-2 text-sm text-faint">Nothing moved this way since the last collection.</p>
        )}
      </div>
    </div>
  );
}
