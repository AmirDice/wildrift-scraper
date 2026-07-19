"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";

// A site-wide nudge shown above the footer on every page EXCEPT the ones it
// would link to (linking a page back to itself is noise). While the build tools
// are held back it points at the meta pages instead of the two flagship tools.
type Cta = { href: string; title: string; badge: string; badgeClass: string; body: string; cta: string; accent: string; ring: string };

const LIVE_TOOLS: Cta[] = [
  {
    href: "/counter", title: "Counter Builder", badge: "new",
    badgeClass: "bg-emerald-400/20 text-emerald-300",
    body: "Give it your champion and the enemy team, get a build tuned to beat exactly who you are facing.",
    cta: "Build against your enemies", accent: "text-emerald-300", ring: "hover:border-emerald-400/40",
  },
  {
    href: "/build", title: "Build Optimizer", badge: "new",
    badgeClass: "bg-accent/20 text-accent",
    body: "Optimal items and runes for every champion, scored by a full fight simulation.",
    cta: "Open the optimizer", accent: "text-accent", ring: "hover:border-accent/40",
  },
];

const META_TOOLS: Cta[] = [
  {
    href: "/meta", title: "Meta Report", badge: "new",
    badgeClass: "bg-emerald-400/20 text-emerald-300",
    body: "The whole meta in charts: tier splits, win rate by class and role, and a win-rate-vs-popularity map of every champion.",
    cta: "Explore the charts", accent: "text-emerald-300", ring: "hover:border-emerald-400/40",
  },
  {
    href: "/tier-list", title: "Tier List", badge: "live",
    badgeClass: "bg-accent/20 text-accent",
    body: "Every champion ranked by the real win rates of its 50 best players, confidence-adjusted.",
    cta: "View the tier list", accent: "text-accent", ring: "hover:border-accent/40",
  },
];

const TOOLS = BUILD_TOOLS_LIVE ? LIVE_TOOLS : META_TOOLS;
const HIDE_ON = BUILD_TOOLS_LIVE ? ["/", "/counter", "/build"] : ["/", "/meta"];

export function ToolsCta() {
  const pathname = usePathname();
  if (HIDE_ON.includes(pathname)) return null;

  return (
    <section className="mx-auto mt-24 max-w-6xl px-5">
      <div className="glass grid gap-4 rounded-2xl border border-line p-6 sm:grid-cols-2 sm:p-8">
        {TOOLS.map((t) => (
          <Link
            key={t.href}
            href={t.href}
            className={`group flex flex-col rounded-xl border border-line bg-white/[0.02] p-5 transition hover:bg-white/[0.04] ${t.ring}`}
          >
            <div className="flex items-center gap-2">
              <h3 className="font-semibold">{t.title}</h3>
              <span className={`rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide ${t.badgeClass}`}>{t.badge}</span>
            </div>
            <p className="mt-1.5 flex-1 text-sm text-muted">{t.body}</p>
            <span className={`mt-3 inline-flex items-center gap-1 text-sm font-semibold ${t.accent}`}>
              {t.cta} <span className="transition-transform group-hover:translate-x-0.5">→</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
