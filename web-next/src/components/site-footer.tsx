import { site } from "@/lib/data";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-line">
      <div className="mx-auto max-w-6xl px-5 py-10 text-center text-sm leading-relaxed text-muted">
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
