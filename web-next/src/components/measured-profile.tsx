import Link from "next/link";
import { Card } from "@/components/ui";
import pulse from "@/data/ladder_pulse.json";

// How the top 50 actually play this champion, measured from their ranked
// match history during the latest collection. Each bar compares the
// champion's average to the cross-champion baseline, so the shape reads as
// an identity: tanky, splitpushing, teamfight-bound, early-aggressive.
// Renders nothing for champions not yet freshly collected.

type Profile = {
  name: string; kda: number | null; teamfight: number | null; gpm: number | null;
  dmgDealt: number | null; dmgTaken: number | null; turret: number | null;
  firstBlood: number | null; mvpRate: number | null; gamesMedian: number | null;
  legendaryTax: number | null; pentas: number;
};

const BARS: { key: keyof Profile; label: string; fmt: (v: number) => string }[] = [
  { key: "dmgDealt", label: "Damage dealt", fmt: (v) => `${(v / 1000).toFixed(1)}k` },
  { key: "dmgTaken", label: "Damage soaked", fmt: (v) => `${(v / 1000).toFixed(1)}k` },
  { key: "turret", label: "Turret pressure", fmt: (v) => `${(v / 1000).toFixed(1)}k` },
  { key: "teamfight", label: "Teamfight presence", fmt: (v) => `${v.toFixed(1)}%` },
  { key: "firstBlood", label: "First blood rate", fmt: (v) => `${v.toFixed(1)}%` },
  { key: "gpm", label: "Gold per minute", fmt: (v) => `${Math.round(v)}` },
];

export function MeasuredProfile({ slug }: { slug: string }) {
  const champs = pulse.champions as Record<string, Profile>;
  const p = champs[slug];
  const base = pulse.baseline as Record<string, number | null>;
  if (!p) return null;

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">How the top 50 play {p.name}</h2>
        <Link href={`/leaderboard?champion=${slug}`}
          className="rounded-full bg-white/10 px-2.5 py-1 text-xs font-semibold text-muted transition hover:text-text">
          See the board
        </Link>
      </div>
      <p className="mt-1 text-sm text-muted">
        Measured from their ranked match history; the marker is the average across all
        freshly collected champions.
      </p>
      <div className="mt-4 space-y-2.5">
        {BARS.map(({ key, label, fmt }) => {
          const v = p[key];
          const b = base[key];
          if (typeof v !== "number" || typeof b !== "number" || b <= 0) return null;
          const rel = v / b; // 1.0 = baseline
          const width = Math.min(100, rel * 50); // baseline lands at 50%
          const above = rel >= 1;
          return (
            <div key={key} className="flex items-center gap-3 text-sm">
              <span className="w-40 shrink-0 text-muted">{label}</span>
              <span className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                <span className={`absolute inset-y-0 left-0 rounded-full ${above ? "bg-accent/80" : "bg-white/25"}`}
                  style={{ width: `${width}%` }} />
                <span className="absolute inset-y-0 left-1/2 w-px bg-white/40" />
              </span>
              <span className="w-14 shrink-0 text-right font-medium tabular-nums">{fmt(v)}</span>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-faint">
        {p.kda != null && <>Average KDA {p.kda.toFixed(1)}. </>}
        {p.legendaryTax != null && (
          <>These players run {p.legendaryTax >= 0 ? `${p.legendaryTax.toFixed(1)}pp better` : `${Math.abs(p.legendaryTax).toFixed(1)}pp worse`} in Legendary Ranked. </>
        )}
        {p.pentas > 0 && <>{p.pentas} pentakills across the board this season.</>}
      </p>
    </Card>
  );
}
