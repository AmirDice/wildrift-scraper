/** was /otp-champions, merged into /meta (2026-10-16): the page's own code, rendered as a section. */
import { Card } from "@/components/ui";
import { OtpChampionExplorer } from "@/components/otp-champion-explorer";
import { site } from "@/lib/data";
import { getGlobalChampions } from "@/lib/cn";
import { getSkillCeilingRows } from "@/lib/regions";


export function OneTrickSection() {
  // EU + NA blended rows (win rate averaged; the one-trick flag and share
  // are measured on the EU boards, which both exports carry). "Best to
  // one-trick" = a board full of dedicated mains AND a win rate above average,
  // ranked by win rate -- ranking by share alone put a 49% champion on top.
  // the blended rows drop skillSpread (two standard deviations do not
  // average); the table column shows the blended ceiling where EU and NA agree
  const ceiling = new Map(getSkillCeilingRows().filter((r) => r.agree).map((r) => [r.slug, r.blended]));
  const champions = getGlobalChampions().map((c) => ({ ...c, skillSpread: ceiling.get(c.slug) ?? null }));
  const flagged = champions.filter((champion) => champion.isOtp && champion.otpScore != null)
    .sort((left, right) => right.wr - left.wr);
  const ranked = champions.filter((champion) => champion.otpScore != null);
  return <section id="one-trick" className="scroll-mt-24 pt-14"><div className="max-w-3xl"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-gold">One-trick rankings</p><h2 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl">Which champions are worth one-tricking?</h2><p className="mt-3 leading-relaxed text-muted">Champions whose boards are dominated by dedicated mains, ranked by win rate across EU, NA and China. The OTP score is the share of a main’s ranked games spent on the champion; the ranking is what those mains actually win.</p></div><div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3"><Card className="p-4"><p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">Champions with a score</p><p className="mt-2 text-2xl font-semibold">{ranked.length}</p></Card><Card className="p-4"><p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">OTP flagged</p><p className="mt-2 text-2xl font-semibold text-gold">{flagged.length}</p></Card><Card className="col-span-2 p-4 sm:col-span-1"><p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">Best to one-trick</p><p className="mt-2 truncate text-xl font-semibold text-accent">{flagged[0]?.name ?? "-"}</p><p className="mt-1 text-xs text-muted">{flagged[0] ? `${flagged[0].wr.toFixed(1)}% WR · OTP score ${flagged[0].otpScore?.toFixed(1)}` : "-"}</p></Card></div><Card className="mt-5 p-4 text-sm leading-relaxed text-muted"><span className="font-semibold text-text">How to read this:</span> the default list is OTP-flagged champions (share in the top quartile) ordered by win rate, the same ranking the WrTrueMeta shorts use. Switch to “by OTP score” to see raw concentration, where a champion can rank high while its mains lose.</Card><div className="mt-8"><OtpChampionExplorer champions={champions} roles={site.roles}/></div></section>;
}
