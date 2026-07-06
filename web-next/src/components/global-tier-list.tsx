import Link from "next/link";
import { TIER_ORDER, tierClass } from "@/lib/data";
import type { Row } from "@/components/cross-server-table";

/* eslint-disable @next/next/no-img-element */

/** Global score = average of the two (already 50%-centered) server win rates. */
export const globalScore = (r: Row) => (r.euWr + r.cnWr) / 2;

function globalTier(wr: number): string {
  if (wr >= 53.5) return "GOD";
  if (wr >= 52) return "S";
  if (wr >= 50.8) return "A";
  if (wr >= 49.5) return "B";
  if (wr >= 48) return "C";
  return "Ass";
}

export function GlobalTierList({ rows }: { rows: Row[] }) {
  const buckets: Record<string, Row[]> = {};
  for (const t of TIER_ORDER) buckets[t] = [];
  for (const r of [...rows].sort((a, b) => globalScore(b) - globalScore(a))) {
    (buckets[globalTier(globalScore(r))] ??= []).push(r);
  }

  return (
    <div className="flex flex-col gap-2.5">
      {TIER_ORDER.map((t) => {
        const champs = buckets[t] ?? [];
        if (champs.length === 0) return null;
        return (
          <div key={t} className="flex items-stretch gap-2.5">
            <div
              className={`grid w-16 shrink-0 place-items-center rounded-xl text-2xl font-black sm:w-20 ${tierClass[t]}`}
            >
              {t}
            </div>
            <div className="glass flex flex-1 flex-wrap content-center gap-3 rounded-xl p-3 sm:gap-4 sm:p-4">
              {champs.map((r) => {
                const g = globalScore(r);
                return (
                  <Link
                    key={r.slug}
                    href={`/champions/${r.slug}`}
                    className="group flex w-[60px] flex-col items-center text-center sm:w-[68px]"
                    title={`${r.name} — global ${g.toFixed(1)}% (EU ${r.euWr.toFixed(1)} / CN ${r.cnWr.toFixed(1)})`}
                  >
                    <img
                      src={r.icon}
                      alt={r.name}
                      width={52}
                      height={52}
                      loading="lazy"
                      className={`h-[52px] w-[52px] rounded-full object-cover transition group-hover:-translate-y-0.5 ${
                        r.isHard ? "ring-2 ring-bad/70" : "ring-1 ring-white/10"
                      }`}
                    />
                    <span className="mt-1.5 w-full truncate text-[0.7rem] font-medium leading-tight">
                      {r.name}
                    </span>
                    <span className="text-[0.7rem] font-semibold text-accent">{g.toFixed(1)}%</span>
                  </Link>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
