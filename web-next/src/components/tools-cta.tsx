"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useBuildToolsVisible } from "@/lib/use-build-tools";

/**
 * Site-wide pointer to the two build tools, shown at the TOP of every page
 * except the ones it links to.
 *
 * It used to sit above the footer, which meant a visitor only met the tools
 * after scrolling a whole page of tier data. These are the things we most want
 * people to try, so they go first -- and they are kept deliberately small, two
 * across even on a narrow phone, so they introduce the tools without pushing
 * the page's actual content below the fold.
 *
 * "Build Studio" rather than "Build Optimizer": the page is a studio in fact
 * (recommended builds, a generator and a custom lab, as tabs), "optimizer"
 * promises a single machine answer that the tool deliberately does not give,
 * and it pairs better with "Counter Builder" than two -er nouns do.
 */
type Cta = {
  href: string;
  title: string;
  short: string;
  badge: string;
  badgeClass: string;
  secondBadge?: string;
  secondBadgeClass?: string;
  body: string;
  accent: string;
  ring: string;
};

const LIVE_TOOLS: Cta[] = [
  {
    href: "/build", title: "Build Studio", short: "Build Studio",
    badge: "new", badgeClass: "bg-emerald-400/20 text-emerald-300",
    secondBadge: "beta", secondBadgeClass: "bg-gold/20 text-gold",
    body: "Generate by playstyle or craft with live item, rune and ability stats.",
    accent: "text-accent", ring: "hover:border-accent/40",
  },
  {
    href: "/build?tab=counter", title: "Build vs Enemy Team", short: "vs Enemy",
    badge: "new", badgeClass: "bg-emerald-400/20 text-emerald-300",
    secondBadge: "beta", secondBadgeClass: "bg-gold/20 text-gold",
    body: "A build tuned to beat the exact team you are facing.",
    accent: "text-emerald-300", ring: "hover:border-emerald-400/40",
  },
];

const META_TOOLS: Cta[] = [
  {
    href: "/meta", title: "Meta Report", short: "Meta",
    badge: "new", badgeClass: "bg-emerald-400/20 text-emerald-300",
    body: "The whole meta in charts: tiers, classes, roles.",
    accent: "text-emerald-300", ring: "hover:border-emerald-400/40",
  },
  {
    href: "/tier-list", title: "Tier List", short: "Tier List",
    badge: "live", badgeClass: "bg-accent/20 text-accent",
    body: "Every champion ranked by its 50 best players.",
    accent: "text-accent", ring: "hover:border-accent/40",
  },
];

export function ToolsCta() {
  const pathname = usePathname();
  // Beta invitees get the real tools promoted; everyone else gets the meta
  // pages, so the CTA never points somewhere the visitor cannot go.
  const live = useBuildToolsVisible();
  const TOOLS = live ? LIVE_TOOLS : META_TOOLS;
  const HIDE_ON = live ? ["/", "/counter", "/build"] : ["/", "/meta"];
  if (HIDE_ON.includes(pathname)) return null;
  // Champion detail pages open with a full-bleed hero banner, and a card strip
  // above a hero reads as a mistake. Those pages render <ToolsCta /> themselves,
  // just below the banner, so the global copy sits this one out.
  if (pathname.startsWith("/champions/")) return null;

  return (
    <section className="mx-auto mt-4 max-w-6xl px-5">
      {/* Two across at every width: on a phone these are the first thing under
          the nav, so they must not cost more than one short row. */}
      <div className="grid grid-cols-2 gap-2 sm:gap-3">
        {TOOLS.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            className={`glass-hover group flex flex-col rounded-xl border border-line bg-white/[0.03] p-3 transition hover:bg-white/[0.05] sm:p-4 ${t.ring}`}
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <h3 className="text-sm font-semibold leading-tight sm:text-base">
                <span className="sm:hidden">{t.short}</span>
                <span className="hidden sm:inline">{t.title}</span>
              </h3>
              <span className={`rounded px-1.5 py-0.5 text-[0.55rem] font-bold uppercase tracking-wide ${t.badgeClass}`}>
                {t.badge}
              </span>
              {t.secondBadge && (
                <span className={`rounded px-1.5 py-0.5 text-[0.55rem] font-bold uppercase tracking-wide ${t.secondBadgeClass}`}>
                  {t.secondBadge}
                </span>
              )}
            </div>
            {/* The description is the first thing to go on a narrow screen. */}
            <p className="mt-1 hidden flex-1 text-xs text-muted sm:block">{t.body}</p>
            <span className={`mt-2 inline-flex items-center gap-1 text-xs font-semibold ${t.accent}`}>
              Open <span className="transition-transform group-hover:translate-x-0.5">→</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
