import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getChampion, getChampions, championsInRole, tierText, type Champion } from "@/lib/data";
import { getCnBySlug } from "@/lib/cn";
import { getMatchups } from "@/lib/counters";
import { getSkewBySlug } from "@/lib/skew";
import { Container, TierChip, ChampionAvatar, Card } from "@/components/ui";
import { BracketCurve } from "@/components/bracket-curve";

export function generateStaticParams() {
  return getChampions().map((c) => ({ slug: c.slug }));
}

export async function generateMetadata(
  props: PageProps<"/champions/[slug]">
): Promise<Metadata> {
  const { slug } = await props.params;
  const c = getChampion(slug);
  if (!c) return { title: "Champion not found" };
  const title = `${c.name} Wild Rift Win Rate, Tier & Stats`;
  const desc = `${c.name} is ${c.tier} tier in Wild Rift with a ${c.wr.toFixed(1)}% top-50 EU win rate. See ${c.name}'s stats, best player and role.`;
  return {
    title,
    description: desc,
    alternates: { canonical: `/champions/${c.slug}` },
    openGraph: { title, description: desc, images: [c.splash] },
    twitter: { card: "summary_large_image", title, description: desc, images: [c.splash] },
  };
}

export default async function ChampionPage(props: PageProps<"/champions/[slug]">) {
  const { slug } = await props.params;
  const c = getChampion(slug);
  if (!c) notFound();

  const cn = getCnBySlug(c.slug);
  const skew = getSkewBySlug(c.slug);
  const { strong, weak } = getMatchups(c.slug);

  const related = championsInRole(c.role)
    .filter((x) => x.slug !== c.slug)
    .slice(0, 6);

  const stats = [
    { label: "Tier", value: c.tier, cls: tierText[c.tier] },
    { label: "Win rate", value: `${c.wr.toFixed(1)}%`, cls: "text-accent" },
    { label: "Ceiling WR", value: c.maxWr != null ? `${c.maxWr.toFixed(1)}%` : "-", cls: "text-gold" },
    { label: "Median games", value: c.medianGames != null ? c.medianGames.toLocaleString() : "-", cls: "" },
  ];

  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-line">
        <div
          className="absolute inset-0 bg-cover opacity-40"
          style={{ backgroundImage: `url(${c.splash})`, backgroundPosition: "center 22%" }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-bg via-bg/85 to-bg/30" />
        <div className="absolute inset-0 bg-gradient-to-t from-bg to-transparent" />
        <Container className="relative py-14">
          <Link href="/champions" className="text-sm text-muted transition hover:text-text">
            ← All champions
          </Link>
          <div className="mt-5 flex items-center gap-4">
            <ChampionAvatar champion={c} size={72} showBadges={false} />
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{c.name}</h1>
                {c.isOtp && (
                  <span className="rounded bg-gradient-to-br from-orange-400 to-orange-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
                    OTP
                  </span>
                )}
              </div>
              <p className="mt-1 text-muted">
                {c.role} · {c.class} ·{" "}
                <span className={c.isHard ? "text-bad" : ""}>{c.difficultyLabel}</span>
              </p>
            </div>
          </div>
        </Container>
      </section>

      <Container className="py-10">
        {/* Stats */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stats.map((s) => (
            <Card key={s.label} className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">{s.label}</p>
              <p className={`mt-2 text-2xl font-semibold ${s.cls}`}>{s.value}</p>
            </Card>
          ))}
        </div>

        {/* Win rate context */}
        <Card className="mt-6 p-6">
          <h2 className="text-lg font-semibold">{c.name} win rate &amp; tier</h2>
          <p className="mt-2 text-muted">
            {c.name} is currently <span className="font-medium text-text">{c.tier} tier</span> in
            EU Wild Rift. Its win rate is shown{" "}
            <span className="font-medium text-text">relative to the average champion</span> (50% =
            average), currently{" "}
            <span className="font-medium text-accent">{c.wr.toFixed(1)}%</span>. These are each
            champion&rsquo;s top-50 mains, so we centre the scale to make the gap between champions
            readable. The best {c.name} main still peaks at{" "}
            <span className="font-medium text-gold">
              {c.maxWr != null ? `${c.maxWr.toFixed(1)}%` : "-"}
            </span>{" "}
            (a real win rate).
          </p>
        </Card>

        {/* Strong / weak against */}
        {(strong.length > 0 || weak.length > 0) && (
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <Matchups title={`${c.name} is strong against`} accent="text-accent" champions={strong} />
            <Matchups title={`${c.name} is weak against`} accent="text-bad" champions={weak} />
          </div>
        )}

        {/* Win rate by region */}
        <Card className="mt-6 p-6">
          <h2 className="text-lg font-semibold">Win rate by region</h2>
          <p className="mt-1 text-sm text-muted">
            Same 50%-centred scale across servers, so you can compare regions directly.
          </p>
          <div className="mt-4 grid grid-cols-3 gap-3">
            <RegionStat label="EU" wr={c.wr} sub={`${c.tier} tier · top 50`} />
            {cn ? (
              <RegionStat
                label="CN"
                wr={cn.wr}
                sub={`${cn.role} · ${cn.cnPickRate.toFixed(1)}% pick · Challenger+`}
              />
            ) : (
              <RegionStat label="CN" />
            )}
            <RegionStat label="NA" />
          </div>
        </Card>

        {/* Win rate by rank (CN skill brackets) */}
        {skew && (
          <Card className="mt-6 p-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold">{c.name} win rate by rank</h2>
              <Link
                href="/ranks"
                className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                  skew.climbing
                    ? "bg-emerald-400/15 text-emerald-300"
                    : skew.stomper
                      ? "bg-rose-400/15 text-rose-300"
                      : "bg-white/10 text-muted"
                }`}
              >
                {skew.climbing ? "Scales with elo" : skew.stomper ? "Falls off up top" : "Stable across ranks"}
              </Link>
            </div>
            <p className="mt-1 text-sm text-muted">
              How {c.name} performs from the whole ladder up to China&rsquo;s Challenger+ bracket.
            </p>
            <div className="mt-4 flex justify-center">
              <BracketCurve curve={skew.curve} skew={skew.skew} labeled width={460} height={150} className="h-auto w-full max-w-[460px]" />
            </div>
            <p className="mt-3 text-sm text-muted">
              {skew.climbing ? (
                <>
                  {c.name} <span className="font-medium text-emerald-300">gains {skew.skew.toFixed(1)} win rate</span>{" "}
                  from all ranks to Challenger+, a high-skill pick that rewards mastery.
                </>
              ) : skew.stomper ? (
                <>
                  {c.name} <span className="font-medium text-rose-300">loses {Math.abs(skew.skew).toFixed(1)} win rate</span>{" "}
                  against Challenger+ play, great for climbing, less so at the very top.
                </>
              ) : (
                <>{c.name} holds a steady win rate across every rank, a reliable, elo-agnostic pick.</>
              )}
            </p>
          </Card>
        )}

        {/* Best player */}
        <Card className="mt-6 p-6">
          <h2 className="text-lg font-semibold">Best {c.name} player</h2>
          {c.bestPlayer ? (
            <p className="mt-2 text-muted">
              The best {c.name} player tracked on EU is{" "}
              <span className="font-medium text-text">{c.bestPlayer.player}</span>
              {c.bestPlayer.rank ? ` (rank #${c.bestPlayer.rank})` : ""}, with a
              confidence-adjusted win rate of{" "}
              <span className="font-medium text-accent">
                {c.bestPlayer.confidence_wr != null
                  ? `${c.bestPlayer.confidence_wr.toFixed(1)}%`
                  : "-"}
              </span>
              . This uses the Wilson lower bound, so it favours proven high-volume performance over
              a lucky streak.
            </p>
          ) : (
            <p className="mt-2 text-muted">Best-player data is being collected.</p>
          )}
        </Card>

        {/* Related */}
        {related.length > 0 && (
          <div className="mt-10">
            <h2 className="mb-4 text-lg font-semibold">Other {c.role} champions</h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {related.map((r) => (
                <Link
                  key={r.slug}
                  href={`/champions/${r.slug}`}
                  className="glass glass-hover flex flex-col items-center gap-2 rounded-xl p-3 text-center"
                >
                  <ChampionAvatar champion={r} size={48} />
                  <span className="truncate text-sm font-medium">{r.name}</span>
                  <div className="flex items-center gap-1.5">
                    <TierChip tier={r.tier} />
                    <span className="text-xs font-semibold text-accent">{r.wr.toFixed(1)}%</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </Container>
    </>
  );
}

function Matchups({
  title,
  accent,
  champions,
}: {
  title: string;
  accent: string;
  champions: Champion[];
}) {
  return (
    <Card className="p-5">
      <h2 className={`text-sm font-semibold ${accent}`}>{title}</h2>
      {champions.length === 0 ? (
        <p className="mt-3 text-sm text-muted">No clear matchups tracked yet.</p>
      ) : (
        <div className="mt-3 flex flex-wrap gap-3">
          {champions.slice(0, 8).map((m) => (
            <Link
              key={m.slug}
              href={`/champions/${m.slug}`}
              className="group flex w-[52px] flex-col items-center gap-1 text-center"
            >
              <ChampionAvatar champion={m} size={44} showBadges={false} />
              <span className="w-full truncate text-[0.65rem] text-muted transition group-hover:text-text">
                {m.name}
              </span>
            </Link>
          ))}
        </div>
      )}
    </Card>
  );
}

function RegionStat({ label, wr, sub }: { label: string; wr?: number; sub?: string }) {
  if (wr == null) {
    return (
      <div className="glass rounded-xl p-4 text-center">
        <div className="text-xs font-bold uppercase tracking-wide text-faint">{label}</div>
        <div className="mt-2 text-sm text-faint">soon</div>
      </div>
    );
  }
  return (
    <div className="glass rounded-xl p-4 text-center">
      <div className="text-xs font-bold uppercase tracking-wide text-faint">{label}</div>
      <div className={`mt-1.5 text-2xl font-semibold ${wr >= 50 ? "text-accent" : "text-muted"}`}>
        {wr.toFixed(1)}%
      </div>
      {sub && <div className="mt-0.5 text-[0.7rem] leading-tight text-muted">{sub}</div>}
    </div>
  );
}
