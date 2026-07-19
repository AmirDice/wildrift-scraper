"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";

type NavItem = { href: string; label: string; badge?: string; desc?: string };
type NavGroup = { label: string; items: NavItem[] };
type NavEntry = NavItem | NavGroup;

const isGroup = (e: NavEntry): e is NavGroup => "items" in e;

// The Builds menu leads with the two flagship tools when they are live; until
// then it collapses to a flat "Items" link so nothing points at a hidden page.
const buildsEntry: NavEntry = BUILD_TOOLS_LIVE
  ? {
      label: "Builds",
      items: [
        { href: "/build", label: "Build Optimizer", badge: "new", desc: "Optimal items & runes per champion" },
        { href: "/counter", label: "Counter Builder", badge: "new", desc: "Build vs your exact enemy team" },
        { href: "/items", label: "Items", desc: "Stats, passives & costs" },
      ],
    }
  : { href: "/items", label: "Items" };

// Flat links stay flat; the rest is grouped so every page has a home in the nav.
// The data pages that used to be orphaned -- Global, Consistency, News, Patch,
// Recap -- are all linked.
const NAV: NavEntry[] = [
  { href: "/tier-list", label: "Tier List" },
  { href: "/champions", label: "Champions" },
  buildsEntry,
  {
    label: "Meta",
    items: [
      { href: "/meta", label: "Meta Report", badge: "new", desc: "Charts & visualizations" },
      { href: "/ranks", label: "Win Rate by Rank", desc: "Low elo vs high elo picks" },
      { href: "/compare", label: "Compare Champions", desc: "Two champions side by side" },
      { href: "/rising", label: "Rising Picks", desc: "What China plays before the West" },
      { href: "/global", label: "Global Win Rates", desc: "EU vs CN cross-server meta" },
      { href: "/consistency", label: "Consistency", desc: "Skill ceiling & reliability" },
      { href: "/leaderboard", label: "Leaderboards", desc: "Top 50 players per champion" },
    ],
  },
  {
    label: "Updates",
    items: [
      { href: "/news", label: "Latest News", desc: "Patches, champions & updates" },
      { href: "/patch", label: "Patch 7.2 Breakdown", desc: "What changed this patch" },
      { href: "/recap", label: "Season Recap", desc: "Season 22 in review" },
    ],
  },
  { href: "/methodology", label: "Methodology" },
];

function NavBadge({ text }: { text: string }) {
  const cls = text === "new"
    ? "bg-emerald-400/20 text-emerald-300"
    : "bg-accent/20 text-accent";
  return (
    <span className={`rounded px-1 py-0.5 text-[0.55rem] font-bold uppercase leading-none tracking-wide ${cls}`}>
      {text}
    </span>
  );
}

function Wordmark() {
  return (
    <Link href="/" className="flex items-center transition hover:opacity-90" aria-label="WrTrueMeta home">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/logo.png"
        alt="WrTrueMeta"
        style={{ height: "clamp(20px, 4vw, 26px)", width: "auto" }}
      />
    </Link>
  );
}

function Caret({ open }: { open: boolean }) {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round"
      className={`transition-transform ${open ? "rotate-180" : ""}`}>
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

/** Desktop dropdown: opens on hover and on click, closes on leave / outside click. */
function DesktopGroup({ group, active }: { group: NavGroup; active: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <div
      ref={ref}
      className="relative"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={`flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
          active || open ? "text-text bg-white/[0.06]" : "text-muted hover:text-text hover:bg-white/[0.04]"
        }`}
      >
        {group.label}
        <Caret open={open} />
      </button>
      {open && (
        <div className="absolute right-0 top-full w-64 pt-2">
          <div className="rounded-xl border border-line bg-[#0e1322] p-1.5 shadow-2xl">
            {group.items.map((it) => (
              <Link
                key={it.href}
                href={it.href}
                onClick={() => setOpen(false)}
                className="flex flex-col rounded-lg px-3 py-2 transition hover:bg-white/[0.06]"
              >
                <span className="flex items-center gap-1.5 text-sm font-medium text-text">
                  {it.label}
                  {it.badge && <NavBadge text={it.badge} />}
                </span>
                {it.desc && <span className="mt-0.5 text-[0.7rem] text-faint">{it.desc}</span>}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function SiteNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const isActive = (href: string) => pathname === href || pathname.startsWith(href + "/");
  const groupActive = (g: NavGroup) => g.items.some((it) => isActive(it.href));

  return (
    <header className="sticky top-0 z-50 border-b border-line bg-bg/80 backdrop-blur-xl">
      <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
        <Wordmark />

        <div className="hidden items-center gap-1 md:flex">
          {NAV.map((e) =>
            isGroup(e) ? (
              <DesktopGroup key={e.label} group={e} active={groupActive(e)} />
            ) : (
              <Link
                key={e.href}
                href={e.href}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  isActive(e.href) ? "text-text bg-white/[0.06]" : "text-muted hover:text-text hover:bg-white/[0.04]"
                }`}
              >
                {e.label}
                {e.badge && <NavBadge text={e.badge} />}
              </Link>
            ),
          )}
        </div>

        <button
          onClick={() => setOpen((v) => !v)}
          className="grid h-10 w-10 place-items-center rounded-lg text-muted transition hover:bg-white/[0.06] hover:text-text md:hidden"
          aria-label="Toggle menu"
          aria-expanded={open}
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            {open ? (
              <>
                <line x1="6" y1="6" x2="18" y2="18" />
                <line x1="18" y1="6" x2="6" y2="18" />
              </>
            ) : (
              <>
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </>
            )}
          </svg>
        </button>
      </nav>

      {open && (
        <div className="max-h-[75vh] overflow-y-auto border-t border-line bg-bg/95 px-4 py-3 md:hidden">
          <div className="flex flex-col gap-1">
            {NAV.map((e) =>
              isGroup(e) ? (
                <div key={e.label} className="mt-1">
                  <p className="px-3 pb-1 pt-2 text-[0.6rem] font-bold uppercase tracking-wide text-faint">{e.label}</p>
                  {e.items.map((it) => (
                    <Link
                      key={it.href}
                      href={it.href}
                      onClick={() => setOpen(false)}
                      className={`flex items-center gap-1.5 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                        isActive(it.href) ? "text-accent bg-accent/10" : "text-muted hover:text-text hover:bg-white/[0.04]"
                      }`}
                    >
                      {it.label}
                      {it.badge && <NavBadge text={it.badge} />}
                    </Link>
                  ))}
                </div>
              ) : (
                <Link
                  key={e.href}
                  href={e.href}
                  onClick={() => setOpen(false)}
                  className={`flex items-center gap-1.5 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                    isActive(e.href) ? "text-accent bg-accent/10" : "text-muted hover:text-text hover:bg-white/[0.04]"
                  }`}
                >
                  {e.label}
                  {e.badge && <NavBadge text={e.badge} />}
                </Link>
              ),
            )}
          </div>
        </div>
      )}
    </header>
  );
}
