import { Card, SectionHeading } from "@/components/ui";
import pulse from "@/data/ladder_pulse.json";
import items from "@/data/items.json";
import runeIcons from "@/data/rune_icons.json";

// What the top 50 of every collected champion actually equip, ordered.
// Win rates here are games-weighted and only shown once a bucket clears 200
// games, so one lucky player cannot top a table. They are top-50 win rates,
// so they all sit high; what matters is the gap between them.

type Row = { name: string; count: number; wr: number | null; slug?: string; tree?: string };

const TREE_TONE: Record<string, string> = {
  Precision: "bg-amber-400/70",
  Resolve: "bg-emerald-400/70",
  Sorcery: "bg-sky-400/70",
  Domination: "bg-rose-400/70",
};

function icons(): Record<string, string> {
  const m: Record<string, string> = {};
  for (const it of items as { slug: string; icon?: string }[]) if (it.icon) m[it.slug] = it.icon;
  return m;
}

function Bar({ value, max, tone }: { value: number; max: number; tone: string }) {
  return (
    <span className="hidden h-2 rounded-full sm:inline-block"
      style={{ width: `${Math.max(4, (value / max) * 110)}px` }}>
      <span className={`block h-full rounded-full ${tone}`} />
    </span>
  );
}

function UsageList({ rows, art, tone = "bg-accent/70", showTree = false }: {
  rows: Row[]; art?: Record<string, string>; tone?: string; showTree?: boolean;
}) {
  const max = Math.max(...rows.map((r) => r.count), 1);
  return (
    <ul className="space-y-1.5">
      {rows.map((r, i) => (
        <li key={r.name} className="flex items-center gap-2 text-sm">
          <span className="w-5 shrink-0 text-right text-xs tabular-nums text-faint">{i + 1}</span>
          {art && art[r.slug ?? r.name] && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={art[r.slug ?? r.name]} alt="" width={22} height={22}
              className="h-[22px] w-[22px] shrink-0 rounded bg-black/30 object-contain ring-1 ring-white/10" />
          )}
          <span className="min-w-0 flex-1 truncate">{r.name}</span>
          <Bar value={r.count} max={max}
            tone={showTree && r.tree ? TREE_TONE[r.tree] ?? tone : tone} />
          <span className="w-10 shrink-0 text-right text-xs tabular-nums text-muted">{r.count}</span>
          <span className="w-12 shrink-0 text-right text-xs tabular-nums text-accent">
            {r.wr != null ? `${r.wr.toFixed(1)}%` : "-"}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function UsageTables() {
  const art = icons();
  const runeArt = runeIcons as Record<string, string>;
  const trees = pulse.treeMeta as Row[];
  const keystones = pulse.keystoneAll as Row[];
  const minors = pulse.minorMeta as Row[];
  const allItems = pulse.itemAll as Row[];
  if (!trees?.length) return null;

  const played = (r: Row) => r.count > 0;
  const leastItems = [...allItems].filter(played).reverse().slice(0, 10);
  const leastMinors = [...minors].filter(played).reverse().slice(0, 8);

  // "wins the most": best games-weighted win rate among choices with a real
  // sample, not the most popular one.
  const bestOf = (rows: Row[], min = 20) =>
    [...rows].filter((r) => r.wr != null && r.count >= min)
      .sort((a, b) => (b.wr ?? 0) - (a.wr ?? 0))[0];
  const bestKeystone = bestOf(keystones);
  const bestItem = bestOf(allItems, 30);
  const bestMinor = bestOf(minors, 30);

  return (
    <div className="mt-10">
      <SectionHeading
        title="What high elo actually runs"
        subtitle={`Every rune and item equipped by ${pulse.nPlayers.toLocaleString()} top-50 players, ordered by use. The percentage is their games-weighted win rate.`}
      />

      {(bestKeystone || bestItem || bestMinor) && (
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          {[["Best keystone", bestKeystone], ["Best minor rune", bestMinor],
            ["Best item", bestItem]].map(([label, row]) => {
            const r = row as Row | undefined;
            if (!r) return null;
            return (
              <Card key={label as string} className="flex items-center gap-3 p-4">
                {(art[r.slug ?? ""] || runeArt[r.name]) && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={art[r.slug ?? ""] || runeArt[r.name]} alt="" width={34} height={34}
                    className="h-[34px] w-[34px] rounded bg-black/30 object-contain ring-1 ring-white/10" />
                )}
                <div className="min-w-0">
                  <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">
                    {label as string}
                  </p>
                  <p className="truncate text-sm font-medium">{r.name}</p>
                </div>
                <span className="ml-auto shrink-0 text-lg font-semibold text-accent tabular-nums">
                  {r.wr?.toFixed(1)}%
                </span>
              </Card>
            );
          })}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">
            Rune trees by use
          </p>
          <UsageList rows={trees} showTree tone="bg-accent/70" />
        </Card>
        <Card className="p-5">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">
            Keystones by use
          </p>
          <UsageList rows={keystones.slice(0, 10)} art={runeArt} />
        </Card>
        <Card className="p-5">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">
            Most used minor runes
          </p>
          <UsageList rows={minors.slice(0, 10)} art={runeArt} showTree />
        </Card>
        <Card className="p-5">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">
            Least used minor runes
          </p>
          <UsageList rows={leastMinors} art={runeArt} showTree tone="bg-white/25" />
        </Card>
        <Card className="p-5">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">
            Most used items
          </p>
          <UsageList rows={allItems.slice(0, 12)} art={art} tone="bg-gold/60" />
        </Card>
        <Card className="p-5">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">
            Least used items
          </p>
          <p className="mb-2 text-[0.7rem] text-faint">
            Items that were built at least once. Anything absent was never built at all.
          </p>
          <UsageList rows={leastItems} art={art} tone="bg-white/25" />
        </Card>
      </div>
    </div>
  );
}
