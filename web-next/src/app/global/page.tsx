import type { Metadata } from "next";
import { getChampions, site } from "@/lib/data";
import { getCnBySlug, CN_META } from "@/lib/cn";
import { Container } from "@/components/ui";
import { CrossServerTable, type Row } from "@/components/cross-server-table";
import { GlobalTierList } from "@/components/global-tier-list";

export const metadata: Metadata = {
  title: "Global Win Rates — EU vs CN Cross-Server Meta",
  description:
    "Compare Wild Rift champion win rates across servers (EU vs China). Champions strong on every server are the safest, genuinely strong picks — filter to those with one click.",
  alternates: { canonical: "/global" },
};

export default function GlobalPage() {
  const rows: Row[] = [];
  for (const c of getChampions()) {
    const cn = getCnBySlug(c.slug);
    if (!cn) continue;
    rows.push({
      slug: c.slug,
      name: c.name,
      icon: c.icon,
      role: c.role,
      isHard: c.isHard,
      euWr: c.wr,
      euTier: c.tier,
      cnWr: cn.wr,
      cnTier: cn.tier,
    });
  }

  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Global Win Rates</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Every champion&rsquo;s win rate on <span className="text-text">EU</span> (top-50 mains) and{" "}
        <span className="text-text">CN</span> ({CN_META.bracket}), on the same 50%-centred scale.
        Champions strong on <span className="text-emerald-300">both servers</span> are the safest
        picks — a big <span className="text-text">Gap</span> means a champion is server-specific
        (meta or playstyle), not universally strong.
      </p>

      <h2 className="mt-9 text-xl font-semibold tracking-tight">Global tier list</h2>
      <p className="mt-1 text-sm text-muted">
        Ranked by combined EU + CN win rate — the champions strongest across both servers.
      </p>
      <div className="mt-5">
        <GlobalTierList rows={rows} />
      </div>

      <h2 className="mt-10 text-xl font-semibold tracking-tight">All champions, side by side</h2>
      <div className="mt-5">
        <CrossServerTable rows={rows} roles={site.roles} />
      </div>

      <p className="mt-6 text-xs text-faint">
        {rows.length} champions with data on both servers. EU updated {site.collectedOn ?? "recently"}
        {CN_META.date ? ` · CN updated ${CN_META.date.replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3")}` : ""}.
      </p>
    </Container>
  );
}
