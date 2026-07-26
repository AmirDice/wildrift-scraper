import { Card } from "@/components/ui";
import type { ChampionChange, ChampionHistorySummary } from "@/lib/champion-history";

const clean = (text: string) => text
  .replaceAll("â†’", "→").replaceAll("â€™", "’")
  .replaceAll("â€“", "–").replaceAll("Â", "").trim();

function dateLabel(value: string | null) {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("en", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(value));
}

export function ChampionHistory({ name, changes, summary }: { name: string; changes: ChampionChange[]; summary: ChampionHistorySummary | null }) {
  if (!changes.length) return <Card className="p-6"><h2 className="text-lg font-semibold">Patch history</h2><p className="mt-2 text-sm text-muted">No official patch changes have been indexed for {name} yet.</p></Card>;

  return (
    <div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Card className="p-4"><p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">Last balance change</p><p className="mt-2 text-xl font-semibold text-accent">Patch {summary?.lastBalancePatch ?? changes.find((x) => !x.modeOnly)?.patch ?? "-"}</p><p className="mt-1 text-xs text-muted">{dateLabel(summary?.lastBalanceAt ?? null)}</p></Card>
        <Card className="p-4"><p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">Tracked updates</p><p className="mt-2 text-xl font-semibold">{summary?.totalChanges ?? changes.length}</p><p className="mt-1 text-xs text-muted">Official Riot patch entries</p></Card>
        <Card className="col-span-2 p-4 sm:col-span-1"><p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">Special modes</p><p className="mt-2 text-xl font-semibold text-gold">{summary?.modeOnlyChanges ?? changes.filter((x) => x.modeOnly).length}</p><p className="mt-1 text-xs text-muted">Separate from standard balance</p></Card>
      </div>
      <Card className="mt-4 overflow-hidden">
        <div className="border-b border-line/60 p-5"><h2 className="text-lg font-semibold">{name} change timeline</h2><p className="mt-1 text-sm text-muted">Tap an update for the full change. Special-mode updates are clearly labelled.</p></div>
        <div className="divide-y divide-line/60">
          {changes.map((entry, index) => (
            <details key={`${entry.patch}-${entry.publishedAt}-${index}`} className="group" open={index === 0 && !entry.modeOnly}>
              <summary className="flex cursor-pointer list-none items-start gap-3 p-4 transition hover:bg-white/[0.025] sm:p-5">
                <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${entry.modeOnly ? "bg-gold" : "bg-accent"}`} />
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2"><strong>Patch {entry.patch}</strong><span className={`rounded-full px-2 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide ${entry.modeOnly ? "bg-gold/15 text-gold" : "bg-accent/15 text-accent"}`}>{entry.modeOnly ? "Special mode" : entry.kind}</span></span>
                  <span className="mt-1 block line-clamp-2 text-sm text-muted">{clean(entry.summary)}</span>
                  <span className="mt-1 block text-[0.7rem] text-faint">{dateLabel(entry.publishedAt)}</span>
                </span>
                <span className="mt-1 text-muted transition group-open:rotate-180" aria-hidden>⌄</span>
              </summary>
              <div className="border-t border-line/40 bg-black/10 px-4 pb-5 pt-4 sm:px-10">
                <div className="space-y-4">{entry.changes.map((change, i) => <div key={`${change.ability}-${i}`}><h3 className="text-sm font-semibold">{clean(change.ability)}</h3><p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-muted">{clean(change.text)}</p></div>)}</div>
                <a href={entry.url} target="_blank" rel="noreferrer" className="mt-4 inline-flex text-xs font-semibold text-accent hover:underline">Read official Riot patch notes →</a>
              </div>
            </details>
          ))}
        </div>
      </Card>
    </div>
  );
}
