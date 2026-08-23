import Link from "next/link";
import { site } from "@/lib/data";
import { DiscordButton } from "@/components/discord";
import { SupportButton } from "@/components/support";
import { TikTokButton, YouTubeButton } from "@/components/socials";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";

const FOOTER_LINKS = [
  { href: "/tier-list", label: "Tier List" },
  { href: "/global", label: "Global" },
  { href: "/rising", label: "Rising Picks" },
  { href: "/ranks", label: "Win Rate by Rank" },
  { href: "/compare", label: "Compare" },
  { href: "/consistency", label: "Consistency" },
  // Dropped below while the build tools are held back: /build redirects home.
  { href: "/build", label: "Builds" },
  { href: "/items", label: "Items" },
  { href: "/runes-spells", label: "Runes & Spells" },
  { href: "/blog", label: "Guides" },
  { href: "/creators", label: "Creators" },
  { href: "/news", label: "News" },
  { href: "/changes-report", label: "Balance Report" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/methodology", label: "Methodology" },
];

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-line">
      <div className="mx-auto max-w-6xl px-5 py-10 text-center text-sm leading-relaxed text-muted">
        <nav className="mb-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-2">
          {FOOTER_LINKS.filter((l) => BUILD_TOOLS_LIVE || l.href !== "/build").map((l) => (
            <Link key={l.href} href={l.href} className="text-muted transition hover:text-text">
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="mb-6 flex flex-wrap items-center justify-center gap-3">
          <DiscordButton>Join our Discord</DiscordButton>
          <TikTokButton>TikTok</TikTokButton>
          <YouTubeButton>YouTube</YouTubeButton>
          <SupportButton>Buy me a coffee</SupportButton>
        </div>
        <p>
          Questions or feedback? Come say hi in the Discord, or DM{" "}
          <span className="font-medium text-accent">@generalthr4gg</span>.
        </p>
        <p className="mt-1">
          WrTrueMeta is free and has no ads. If it helps you climb,{" "}
          <a
            href="https://buymeacoffee.com/wrtruemeta"
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-gold transition hover:opacity-80"
          >
            buy me a coffee
          </a>{" "}
          to keep the servers running.
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
