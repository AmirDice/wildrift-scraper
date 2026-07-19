import Link from "next/link";
import { site } from "@/lib/data";

const FOOTER_LINKS = [
  { href: "/tier-list", label: "Tier List" },
  { href: "/global", label: "Global" },
  { href: "/rising", label: "Rising Picks" },
  { href: "/ranks", label: "Win Rate by Rank" },
  { href: "/compare", label: "Compare" },
  { href: "/consistency", label: "Consistency" },
  { href: "/build", label: "Builds" },
  { href: "/items", label: "Items" },
  { href: "/news", label: "News" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/methodology", label: "Methodology" },
];

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-line">
      <div className="mx-auto max-w-6xl px-5 py-10 text-center text-sm leading-relaxed text-muted">
        <nav className="mb-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2">
          {FOOTER_LINKS.map((l) => (
            <Link key={l.href} href={l.href} className="text-muted transition hover:text-text">
              {l.label}
            </Link>
          ))}
        </nav>
        <p>
          Questions or feedback? DM{" "}
          <span className="font-medium text-accent">@generalthr4gg</span> on Discord.
        </p>
        {site.collectedOn && (
          <p className="mt-1 text-faint">Data collected {site.collectedOn}.</p>
        )}
        <p className="mt-3 text-xs text-faint">
          Not affiliated with Riot Games. League of Legends &amp; Wild Rift are &copy; Riot Games, Inc.
        </p>
      </div>
    </footer>
  );
}
