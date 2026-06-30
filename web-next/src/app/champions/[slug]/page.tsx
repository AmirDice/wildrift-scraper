import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getChampion, getChampions, championsInRole, tierText } from "@/lib/data";
import { Container, TierChip, ChampionAvatar, Card } from "@/components/ui";

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

  const related = championsInRole(c.role)
    .filter((x) => x.slug !== c.slug)
    .slice(0, 6);

  const stats = [
    { label: "Tier", value: c.tier, cls: tierText[c.tier] },
    { label: "Win rate", value: `${c.wr.toFixed(1)}%`, cls: "text-accent" },
    { label: "Ceiling WR", value: c.maxWr != null ? `${c.maxWr.toFixed(1)}%` : "—", cls: "text-gold" },
    { label: "Median games", value: c.medianGames != null ? c.medianGames.toLocaleString() : "—", cls: "" },
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
            EU Wild Rift, with a games-weighted win rate of{" "}
            <span className="font-medium text-accent">{c.wr.toFixed(1)}%</span> across the top 50
            players. The highest-WR top-50 player sits at{" "}
            <span className="font-medium text-gold">
              {c.maxWr != null ? `${c.maxWr.toFixed(1)}%` : "—"}
            </span>
            . These are elite specialists, so every win rate is above 50% — the signal is the gap
            between champions, not the absolute number.
          </p>
        </Card>

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
                  : "—"}
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
