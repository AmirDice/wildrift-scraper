import { T } from "@/components/t";
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
  // Same glass panel as "at a glance"; each answer sits in a <details>, so it
  // stays in the HTML for crawlers while the page stays compact.
  return (
    <section className="mt-6">
      <JsonLd data={faqJsonLd(faq)} />
      <div className="glass rounded-[1.5rem] border border-white/[0.09] p-5 sm:p-6">
        <h2 className="text-lg font-semibold">{title}</h2>
        <div className="mt-3 divide-y divide-white/[0.07]">
          {faq.map(({ q, a }) => (
            <details key={q} className="group py-3">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-text marker:hidden">
                {q}
                <span aria-hidden className="text-faint transition group-open:rotate-45">+</span>
              </summary>
              <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">{a}</p>
            </details>
          ))}
        </div>
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
            <span className={row.winRate >= 50 ? "text-emerald-300" : "text-rose-300"}>{row.winRate.toFixed(1)}<T>{"% win"}</T></span>
            <span className="text-muted">{row.pickRate.toFixed(1)}<T>{"% pick"}</T></span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * A champion's own pages as a second row of tabs under the header
 * (owner, 2026-11-28): overview, each lane, runes, counters. The current page
 * is highlighted; labels and hrefs follow the page language.
 */
export function ChampionPageLinks({ slug, name, links, current, lang = "en" }: {
  slug: string;
  name: string;
  links: { href: string; label: string }[];
  current: string;
  lang?: string;
}) {
  const href = (path: string) => (lang === "en" ? path : `/${lang}${path}`);
  const label = (path: string) => {
    if (path === `/champions/${slug}`) return <T>{"Overview"}</T>;
    if (path.endsWith("/runes")) return <T>{"Runes"}</T>;
    if (path.endsWith("/counters")) return <T>{"Counters"}</T>;
    const lane = path.split("/").pop() ?? "";
    return <T>{LANE_NAMES[lane] ?? lane}</T>;
  };
  const all = [`/champions/${slug}`, ...links.map((l) => l.href)];
  return (
    <nav aria-label={name} className="mx-auto max-w-[1280px] px-4 pt-4 sm:px-6">
      <div className="glass flex flex-wrap items-center gap-1 rounded-2xl border border-white/[0.09] p-1.5">
        {all.map((path) => (
          <Link
            key={path}
            href={href(path)}
            aria-current={path === current ? "page" : undefined}
            className={`rounded-xl px-3.5 py-2 text-sm font-semibold transition ${path === current ? "bg-white/[0.09] text-text" : "text-muted hover:bg-white/[0.04] hover:text-text"}`}
          >
            {label(path)}
          </Link>
        ))}
      </div>
    </nav>
  );
}

const LANE_NAMES: Record<string, string> = {
  baron: "Baron Lane", jungle: "Jungle", mid: "Mid Lane", dragon: "Dragon Lane", support: "Support",
};
