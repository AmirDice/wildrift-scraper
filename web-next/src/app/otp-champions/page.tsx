import type { Metadata } from "next";
import { Container, Card } from "@/components/ui";
import { OtpChampionExplorer } from "@/components/otp-champion-explorer";
import { getChampions, site } from "@/lib/data";

export const metadata: Metadata = {
  title: "Best OTP Champions in Wild Rift | One-Trick Rankings",
  description: "Rank every Wild Rift champion by one-trick specialization, mastery, win rate and skill spread using real top-player data.",
  alternates: { canonical: "/otp-champions" },
};

export default function OtpChampionsPage() {
  const champions = getChampions();
  const ranked = champions.filter((champion) => champion.otpScore != null).sort((left, right) => (right.otpScore ?? 0) - (left.otpScore ?? 0));
  const flagged = ranked.filter((champion) => champion.isOtp);
  return <Container className="py-10 sm:py-14"><div className="max-w-3xl"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-gold">One-trick rankings</p><h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Which champions attract the strongest specialists?</h1><p className="mt-3 leading-relaxed text-muted">OTP score measures how concentrated a champion’s leaderboard is around dedicated specialists. Compare it with mastery, win rate and skill spread before choosing a champion to master.</p></div><div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3"><Card className="p-4"><p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">Champions ranked</p><p className="mt-2 text-2xl font-semibold">{ranked.length}</p></Card><Card className="p-4"><p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">OTP flagged</p><p className="mt-2 text-2xl font-semibold text-gold">{flagged.length}</p></Card><Card className="col-span-2 p-4 sm:col-span-1"><p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">Top specialist pick</p><p className="mt-2 truncate text-xl font-semibold text-accent">{ranked[0]?.name ?? "-"}</p><p className="mt-1 text-xs text-muted">OTP score {ranked[0]?.otpScore?.toFixed(1) ?? "-"}</p></Card></div><Card className="mt-5 p-4 text-sm leading-relaxed text-muted"><span className="font-semibold text-text">How to read this:</span> a high OTP score means the champion’s strongest results are especially concentrated among dedicated mains. It does not automatically mean the champion is overpowered.</Card><div className="mt-8"><OtpChampionExplorer champions={champions} roles={site.roles}/></div></Container>;
}
