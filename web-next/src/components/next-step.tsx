import Link from "next/link";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";

/**
 * A contextual "where to go next" strip.
 *
 * Traffic is lopsided: over a month the home page drew 690 visitors and the
 * tier list 498, while the Counter Builder saw 110 and the meta report 101 --
 * yet those two are what the site has that others do not. People land on a
 * ranking, read it, and leave, because nothing on the page tells them the
 * tools exist.
 *
 * So every high-traffic page ends by naming the next useful thing in the
 * language of what the reader just did ("you know who is strong, now build
 * one"), rather than a generic nav row. No popups: an interstitial on a stats
 * page is the fastest way to lose someone who came for a number.
 */

type Step = { href: string; title: string; body: string; cta: string; tone?: "accent" | "gold" };

const STEPS: Record<string, Step> = {
  build: {
    href: "/build",
    title: "Now build the champion",
    body: "Generate a full item order, runes and summoners for your champion and playstyle, each choice explained.",
    cta: "Open Build Studio",
    tone: "accent",
  },
  counter: {
    href: "/counter",
    title: "Facing a hard matchup?",
    body: "Enter the enemy team and get a build shaped to beat exactly who you are up against.",
    cta: "Open Counter Builder",
    tone: "gold",
  },
  meta: {
    href: "/meta",
    title: "See the whole meta",
    body: "Cross-server win rates, the China versus Europe gap, skill-bracket splits, and the runes and items high elo actually runs.",
    cta: "Open the meta report",
  },
  tierList: {
    href: "/tier-list",
    title: "Who is strong right now",
    body: "Every champion ranked by the confidence-adjusted win rate of its best players.",
    cta: "See the tier list",
  },
  leaderboard: {
    href: "/leaderboard",
    title: "Learn from the best players",
    body: "The top 50 on every champion, with the builds, runes and per-queue stats they actually run.",
    cta: "Browse leaderboards",
  },
  champions: {
    href: "/champions",
    title: "Dig into one champion",
    body: "Abilities, scaling, matchups and how the top 50 play it.",
    cta: "Browse champions",
  },
};

export function NextStep({ steps }: { steps: (keyof typeof STEPS)[] }) {
  // The build tools are the whole point of the site, but sending people to a
  // page that is still behind a flag would be worse than saying nothing.
  const picked = steps
    .map((k) => STEPS[k])
    .filter((s) => s && (BUILD_TOOLS_LIVE || (s.href !== "/build" && s.href !== "/counter")));
  if (!picked.length) return null;

  return (
    <section className="mt-12 border-t border-line/60 pt-8">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-muted">Where to next</p>
      <div className={`mt-4 grid gap-3 ${picked.length > 1 ? "sm:grid-cols-2" : ""}`}>
        {picked.map((s) => (
          <Link
            key={s.href}
            href={s.href}
            className="glass group flex flex-col rounded-2xl p-5 transition hover:border-accent/40"
          >
            <h3 className="font-semibold">{s.title}</h3>
            <p className="mt-1 flex-1 text-sm text-muted">{s.body}</p>
            <span
              className={`mt-3 text-sm font-bold ${s.tone === "gold" ? "text-gold" : "text-accent"}`}
            >
              {s.cta} <span aria-hidden className="inline-block transition group-hover:translate-x-0.5">→</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
