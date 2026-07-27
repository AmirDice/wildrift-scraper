import Link from "next/link";
import { ChampionAvatar, Card } from "@/components/ui";
import type { Block } from "@/lib/blog";
import { championsInRole, getChampions, type Champion } from "@/lib/data";
import { climbingPicks, stomperPicks } from "@/lib/skew";
import { risingPicks } from "@/lib/gap";
import { getChampionChangeRanking, getMostAdjustedChampions } from "@/lib/champion-change-ranking";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";

interface ListRow {
  champion: Champion;
  metric: string;
  metricClass: string;
  sub: string;
}

/** Resolves a declarative champion list in a post against the live dataset, so
 *  a published post always shows the current patch's answer. */
function resolve(block: Extract<Block, { kind: "champions" }>): ListRow[] {
  const limit = block.limit ?? 8;

  switch (block.source) {
    case "role": {
      return championsInRole(block.role ?? "Jungle")
        .slice(0, limit)
        .map((champion) => ({
          champion,
          metric: `${champion.wr.toFixed(1)}%`,
          metricClass: "text-accent",
          sub: `${champion.class} · ${champion.difficultyLabel}`,
        }));
    }
    case "climbing":
      return climbingPicks(limit).map((skew) => ({
        champion: skew.champion,
        metric: `+${skew.skew.toFixed(1)}`,
        metricClass: "text-emerald-300",
        sub: `${skew.champion.role} · ${skew.low.toFixed(1)}% in Diamond+, ${skew.high.toFixed(1)}% in Challenger`,
      }));
    case "stompers":
      return stomperPicks(limit).map((skew) => ({
        champion: skew.champion,
        metric: `${skew.low.toFixed(1)}%`,
        metricClass: "text-gold",
        sub: `${skew.champion.role} · falls to ${skew.high.toFixed(1)}% in Challenger`,
      }));
    case "rising":
      return risingPicks(limit).map((gap) => ({
        champion: gap.champion,
        metric: `+${gap.gap.toFixed(1)}`,
        metricClass: "text-emerald-300",
        sub: `${gap.champion.role} · CN ${gap.cnWr.toFixed(1)}% vs West ${gap.euWr.toFixed(1)}%`,
      }));
    case "adjusted":
      return getMostAdjustedChampions(getChampions())
        .slice(0, limit)
        .map((entry) => ({
          champion: entry.champion,
          metric: `${entry.totalChanges}×`,
          metricClass: "text-bad",
          sub: `${entry.balanceChanges} standard balance ${entry.balanceChanges === 1 ? "change" : "changes"}${entry.lastBalancePatch ? ` · last in ${entry.lastBalancePatch}` : ""}`,
        }));
    case "unchanged":
      return getChampionChangeRanking(getChampions())
        .filter((entry) => entry.daysSinceBalanceChange != null)
        .slice(0, limit)
        .map((entry) => ({
          champion: entry.champion,
          metric: `${entry.daysSinceBalanceChange!.toLocaleString()}d`,
          metricClass: "text-gold",
          sub: entry.lastBalancePatch ? `Last changed in patch ${entry.lastBalancePatch}` : "No standard change recorded",
        }));
    case "otp":
      return getChampions()
        .filter((champion) => champion.isOtp)
        .slice(0, limit)
        .map((champion) => ({
          champion,
          metric: champion.otpScore != null ? champion.otpScore.toFixed(1) : "-",
          metricClass: "text-gold",
          sub: `${champion.role} · ${champion.wr.toFixed(1)}% win rate`,
        }));
    default:
      return [];
  }
}

export function BlogBody({ blocks }: { blocks: Block[] }) {
  return (
    <div className="mt-8 space-y-5">
      {blocks.map((block, index) => {
        switch (block.kind) {
          case "h2":
            return (
              <h2 key={index} className="pt-4 text-xl font-semibold tracking-tight sm:text-2xl">
                {block.text}
              </h2>
            );
          case "p":
            return (
              <p key={index} className="leading-relaxed text-muted">
                {block.text}
              </p>
            );
          case "ul":
            return (
              <ul key={index} className="space-y-2">
                {block.items.map((item, itemIndex) => (
                  <li key={itemIndex} className="flex gap-2.5 leading-relaxed text-muted">
                    <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent/70" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            );
          case "quote":
            return (
              <blockquote key={index} className="border-l-2 border-accent/50 pl-4 text-lg italic text-text">
                {block.text}
              </blockquote>
            );
          case "cta":
            // Posts written for the launch already point at the build tools;
            // while those are held back the link would only redirect home.
            if (!BUILD_TOOLS_LIVE && /^\/(build|counter)\b/.test(block.href)) return null;
            return (
              <Link
                key={index}
                href={block.href}
                className="glass glass-hover block rounded-2xl border border-accent/25 p-5"
              >
                <span className="block text-sm text-muted">{block.text}</span>
                <span className="mt-2 inline-flex items-center gap-1 font-semibold text-accent">
                  {block.label} <span aria-hidden>→</span>
                </span>
              </Link>
            );
          case "champions": {
            const rows = resolve(block);
            if (rows.length === 0) return null;
            return (
              <Card key={index} className="overflow-hidden">
                <div className="divide-y divide-line/60">
                  {rows.map((row, rowIndex) => (
                    <Link
                      key={row.champion.slug}
                      href={`/champions/${row.champion.slug}`}
                      className="flex items-center gap-3 px-4 py-3 transition hover:bg-white/[0.03]"
                    >
                      <span className="w-5 text-center text-sm font-semibold text-faint">{rowIndex + 1}</span>
                      <ChampionAvatar champion={row.champion} size={36} showBadges={false} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{row.champion.name}</span>
                        <span className="block truncate text-xs text-muted">{row.sub}</span>
                      </span>
                      <span className={`shrink-0 text-sm font-semibold ${row.metricClass}`}>{row.metric}</span>
                    </Link>
                  ))}
                </div>
                {block.note && <p className="border-t border-line/60 px-4 py-2.5 text-xs text-faint">{block.note}</p>}
              </Card>
            );
          }
          default:
            return null;
        }
      })}
    </div>
  );
}
