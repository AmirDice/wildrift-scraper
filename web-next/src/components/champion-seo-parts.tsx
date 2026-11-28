import Link from "next/link";
import { Card } from "@/components/ui";
import { JsonLd } from "@/lib/structured-data";
import { faqJsonLd, type Faq } from "@/lib/champion-seo";
import type { LoadoutRow } from "@/lib/cn-loadouts";

/**
 * Server-rendered pieces for the champion SEO pages. Server-rendered on
 * purpose: the interactive loadout explorer is a client component whose
 * hidden tabs are not in the HTML a crawler reads first.
 */

export function FaqSection({ faq, title }: { faq: Faq; title: string }) {
  if (!faq.length) return null;
  return (
    <section className="mt-10">
      <JsonLd data={faqJsonLd(faq)} />
      <h2 className="text-xl font-semibold">{title}</h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {faq.map(({ q, a }) => (
          <Card key={q} className="p-5">
            <h3 className="text-sm font-semibold text-text">{q}</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-muted">{a}</p>
          </Card>
        ))}
      </div>
    </section>
  );
}

/** One measured row per line: icons, names, win rate and pick rate. */
export function LoadoutRows({ rows, empty }: { rows: LoadoutRow[]; empty?: string }) {
  if (!rows.length) return empty ? <p className="mt-3 text-sm text-faint">{empty}</p> : null;
  return (
    <ul className="mt-3 divide-y divide-white/[0.06]">
      {rows.map((row) => (
        <li key={row.entities.map((e) => e.name).join("+")} className="flex flex-wrap items-center gap-3 py-2.5">
          <span className="flex items-center gap-1.5">
            {row.entities.map((e) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img key={e.name} src={e.icon} alt="" width={30} height={30} className="rounded-md ring-1 ring-white/10" />
            ))}
          </span>
          <span className="min-w-0 flex-1 text-sm text-text">
            {row.entities.map((e, i) => (
              <span key={e.name}>
                {i > 0 && <span className="text-faint"> + </span>}
                {e.href ? <Link href={e.href} className="hover:text-accent">{e.name}</Link> : e.name}
              </span>
            ))}
          </span>
          <span className="flex shrink-0 gap-3 text-xs tabular-nums">
            <span className={row.winRate >= 50 ? "text-emerald-300" : "text-rose-300"}>{row.winRate.toFixed(1)}% win</span>
            <span className="text-muted">{row.pickRate.toFixed(1)}% pick</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Links between a champion's pages, so every SEO page is reachable. */
export function ChampionPageLinks({ slug, name, links }: { slug: string; name: string; links: { href: string; label: string }[] }) {
  return (
    <nav aria-label={`More on ${name}`} className="mt-6 flex flex-wrap gap-2">
      <Link href={`/champions/${slug}`} className="rounded-full border border-white/12 px-3 py-1 text-xs font-semibold text-muted transition hover:text-text">
        {name} overview
      </Link>
      {links.map((l) => (
        <Link key={l.href} href={l.href} className="rounded-full border border-white/12 px-3 py-1 text-xs font-semibold text-muted transition hover:text-text">
          {l.label}
        </Link>
      ))}
    </nav>
  );
}
