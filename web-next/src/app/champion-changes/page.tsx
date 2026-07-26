import type { Metadata } from "next";
import Link from "next/link";
import { Container, Card, ChampionAvatar } from "@/components/ui";
import { ChampionChangeList, type ChampionChangeListEntry } from "@/components/champion-change-list";
import { getChampions } from "@/lib/data";
import {getChampionChangeAge,
  getChampionChangeRanking} from "@/lib/champion-change-ranking";

export const metadata: Metadata = {
  title: "Champion Change History | Wild Rift",
  description: "See how many days every Wild Rift champion has gone without a standard balance change, ordered from longest unchanged to newest update.",
  alternates: { canonical: "/champion-changes" },
};

export default function ChampionChangesPage() {
  const champions = getChampions();
  const ranking = getChampionChangeRanking(champions);
  const entries: ChampionChangeListEntry[] = ranking.map((entry) => ({
    name: entry.champion.name,
    slug: entry.champion.slug,
    icon: entry.champion.icon,
    role: entry.champion.role,
    patch: entry.lastBalancePatch,
    changedAt: entry.lastBalanceAt,
    days: entry.daysSinceBalanceChange,
    href: `/champions/${entry.champion.slug}`,
  }));
  if (!entries.some((entry) => entry.slug === "skarner")) {
    const skarner = getChampionChangeAge("Skarner");
    entries.push({ name: "Skarner", slug: "skarner", icon: "/abilities/skarner-threads-of-vibration.png", role: "Jungle", patch: skarner.lastBalancePatch, changedAt: skarner.lastBalanceAt, days: skarner.daysSinceBalanceChange, href: undefined, note: "Jungle · Player stats pending" });
  }
  entries.sort((left, right) => (right.days ?? -1) - (left.days ?? -1) || left.name.localeCompare(right.name));

  return (
    <Container className="py-10 sm:py-14">
      <div className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">Official patch history</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">How long has every champion gone unchanged?</h1>
        <p className="mt-3 leading-relaxed text-muted">Every champion in the current site roster, ranked by days since their last standard balance change. Special-mode updates are excluded.</p>
      </div>

      {/* Bait for the two build tools. The site-wide CTA already sits at the
          bottom of every page, but people who came for balance history rarely
          scroll to it, so the tools also lead here at the top where the traffic
          actually is. */}
      <div className="mt-8 grid gap-4 md:grid-cols-2">
        <ToolPromo
          href="/counter"
          title="Counter Builder"
          body="Give it your champion and the enemy team, and get a build, runes and item order tuned to beat exactly who you are facing."
          cta="Build against your enemies"
          accent="text-emerald-300"
          ring="hover:border-emerald-400/40"
          badgeClass="bg-gold/20 text-gold"
        />
        <ToolPromo
          href="/build"
          title="Build Optimizer"
          body="Items and runes for every champion, evaluated from current patch data, purchase timing and complete kit synergy."
          cta="Open the optimizer"
          accent="text-accent"
          ring="hover:border-accent/40"
          badgeClass="bg-gold/20 text-gold"
        />
      </div>


      <div className="mt-8">
        <ChampionChangeList entries={entries} />
      </div>
    </Container>
  );
}

/** A promotional card that routes readers into one of the build tools. Uses the
 *  glass card treatment so it reads as part of the site, not an ad. */
function ToolPromo({
  href, title, body, cta, accent, ring, badgeClass,
}: {
  href: string; title: string; body: string; cta: string; accent: string; ring: string; badgeClass: string;
}) {
  return (
    <Link
      href={href}
      className={`group glass glass-hover flex flex-col rounded-2xl border border-line p-5 transition ${ring}`}
    >
      <div className="flex items-center gap-2">
        <h2 className="text-lg font-semibold">{title}</h2>
        <span className={`rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide ${badgeClass}`}>beta</span>
      </div>
      <p className="mt-1.5 flex-1 text-sm leading-relaxed text-muted">{body}</p>
      <span className={`mt-3 inline-flex items-center gap-1 text-sm font-semibold ${accent}`}>
        {cta} <span className="transition-transform group-hover:translate-x-0.5">→</span>
      </span>
    </Link>
  );
}
