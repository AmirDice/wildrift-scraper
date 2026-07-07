import type { Metadata } from "next";
import { getChampions, site } from "@/lib/data";
import { getCnBySlug, CN_META } from "@/lib/cn";
import Link from "next/link";
import { Container } from "@/components/ui";
import { CrossServerTable, type Row } from "@/components/cross-server-table";

export const metadata: Metadata = {
  title: "Global Win Rates | EU vs CN Cross-Server Meta",
  description:
    "Compare Wild Rift champion win rates across servers (EU vs China). Champions strong on every server are the safest, genuinely strong picks; filter to those with one click.",
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
        picks. A big <span className="text-text">Gap</span> means a champion is server-specific
        (meta or playstyle), not universally strong.
      </p>

      <p className="mt-3 text-sm text-muted">
        Looking for the combined ranking as tiers? See the{" "}
        <Link href="/tier-list" className="text-accent hover:underline">
          Global tier list
        </Link>{" "}
        (the &ldquo;Global&rdquo; toggle on the tier list).
      </p>

      <div className="mt-6">
        <CrossServerTable rows={rows} roles={site.roles} />
      </div>

      <p className="mt-6 text-xs text-faint">
        {rows.length} champions with data on both servers. EU updated {site.collectedOn ?? "recently"}
        {CN_META.date ? ` · CN updated ${CN_META.date.replace(/(\d{4})(\d{2})(\d{2})/, "$1-$2-$3")}` : ""}.
      </p>
    </Container>
  );
}
