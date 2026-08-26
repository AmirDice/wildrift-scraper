"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useBuildToolsVisible } from "@/lib/use-build-tools";
import { DiscordNavLink, DISCORD_URL, DiscordIcon } from "@/components/discord";
import { TIKTOK_URL, YOUTUBE_URL, TikTokIcon, YouTubeIcon } from "@/components/socials";
import { SupportNavLink, BUYMEACOFFEE_URL, CoffeeIcon } from "@/components/support";
import { AccountMenu } from "@/components/account-menu";
import { ChampionCombobox, type ComboItem } from "@/components/champion-combobox";

type NavItem = { href: string; label: string; badge?: string; badges?: string[]; desc?: string };
/** `collapsed` folds the group on MOBILE only, behind a tap. Use it for
 *  browse-when-curious sections, never for ones people arrive looking for --
 *  a tap is a wall for anything that needs to be found. */
type NavGroup = { label: string; items: NavItem[]; collapsed?: boolean };
type NavEntry = NavItem | NavGroup;

const isGroup = (e: NavEntry): e is NavGroup => "items" in e;

// The Builds menu leads with the two flagship tools when they are live; until
// then it drops them so nothing points at a page the visitor would be bounced
// from. `live` is per-visitor, not just per-deploy: a beta invite opens the
// tools early, so the menu has to be built at render time rather than module
// scope.
const buildsEntry = (live: boolean): NavEntry => (live
  ? {
      label: "Builds",
      items: [
        { href: "/build", label: "Build Studio", badges: ["new", "v2"], desc: "Generate by playstyle or craft with live stats" },
        { href: "/build?tab=counter", label: "Build vs Enemy Team", badges: ["v2"], desc: "The build that beats their exact five picks" },
        { href: "/draft", label: "Draft Assistant", badges: ["new"], desc: "Bans, picks and the counter build, live in lobby" },
        { href: "/albums", label: "Build Albums", desc: "Save builds & blend with a friend" },
        { href: "/items", label: "Items", desc: "Stats, passives & costs" },
        { href: "/runes-spells", label: "Runes & Spells", desc: "Effects, trees, cooldowns & uses" },
      ],
    }
  : {
      label: "Builds",
      items: [
        { href: "/items", label: "Items", desc: "Stats, passives & costs" },
        { href: "/runes-spells", label: "Runes & Spells", desc: "Effects, trees, cooldowns & uses" },
        { href: "/albums", label: "Build Albums", desc: "Save builds & blend with a friend" },
      ],
    });

// Flat links stay flat; the rest is grouped so every page has a home in the nav.
// The data pages that used to be orphaned -- Global, Consistency, News, Patch,
// Recap -- are all linked.
const navEntries = (buildToolsLive: boolean): NavEntry[] => [
  { href: "/tier-list", label: "Tier List" },
  { href: "/champions", label: "Champions" },
  // PLAYERS is its own group, not a corner of Meta. Everything else on this
  // site is about champions; these three are about people, and they were
  // sitting at the bottom of a nine-item dropdown where nobody found them.
  // Filing them under Champions would have been a category error -- a player
  // is not a champion -- and Tier List is one ranking page, not a hub.
  {
    label: "Players",
    items: [
      { href: "/leaderboard", label: "Leaderboards", desc: "Top 50 players per champion" },
      { href: "/player", label: "Player Search", desc: "Find a player and every champion they rank on" },
      { href: "/hall-of-fame", label: "Hall of Fame", desc: "Ladder records & guild rankings" },
    ],
  },
  buildsEntry(buildToolsLive),
  {
    label: "Meta",
    items: [
      { href: "/meta", label: "Meta Overview", desc: "Builds, win rates & trends" },
      { href: "/movers", label: "Patch Movers", desc: "Biggest winners & losers right now" },
      { href: "/ranks", label: "Win Rate by Skill Bracket", desc: "Diamond+ to Challenger trends" },
      { href: "/compare", label: "Compare Champions", desc: "Two champions side by side" },
      { href: "/rising", label: "Rising Picks", desc: "What China plays before the West" },
      { href: "/regions", label: "EU vs NA vs China", desc: "Which champions are region-specific" },
      { href: "/global", label: "Global Win Rates", desc: "EU vs CN cross-server meta" },
      { href: "/consistency", label: "Consistency", desc: "Skill ceiling & reliability" },
    ],
  },
  {
    label: "Updates",
    collapsed: true,
    items: [
      { href: "/blog", label: "Guides", desc: "Best picks per role, climbing & meta reads" },
      { href: "/creators", label: "Creators", desc: "Wild Rift channels still uploading" },
      { href: "/news", label: "Latest News", desc: "Patches, champions & updates" },
      { href: "/champion-changes", label: "Balance Report", desc: "Most changed & never changed" },
    ],
  },
  // Methodology lives in the FOOTER, not here. It is a trust page rather than
  // a destination -- the people who open it are deciding whether to believe
  // the numbers, and they look for it at the bottom of the page, which is
  // where every site puts this. Keeping it out of the top bar buys a slot for
  // Players without costing a link (footer + sitemap still carry it).
];

function NavBadge({ text }: { text: string }) {
  const cls = text === "new"
    ? "bg-emerald-400/20 text-emerald-300"
    : text === "beta"
      ? "bg-gold/20 text-gold"
      : "bg-accent/20 text-accent";
  return (
    <span className={`rounded px-1 py-0.5 text-[0.55rem] font-bold uppercase leading-none tracking-wide ${cls}`}>
      {text}
    </span>
  );
}

function NavBadges({ item }: { item: NavItem }) {
  const badges = item.badges ?? (item.badge ? [item.badge] : []);
  return badges.map((badge) => <NavBadge key={badge} text={badge} />);
}

function SearchGlyph() {
  return (
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  );
}

function NavSearch({ champions }: { champions: ComboItem[] }) {
  const router = useRouter();
  const ref = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label="Search champions"
        aria-expanded={open}
        className={`grid h-10 w-10 place-items-center rounded-lg transition ${open ? "bg-white/[0.06] text-text" : "text-muted hover:bg-white/[0.06] hover:text-text"}`}
      >
        <SearchGlyph />
      </button>
      {open && (
        <div className="fixed left-4 right-4 top-[4.5rem] z-[70] rounded-2xl border border-line bg-surface-2 p-3 shadow-2xl md:absolute md:left-auto md:right-0 md:top-full md:mt-2 md:w-80">
          <ChampionCombobox
            champions={champions}
            placeholder="Search champions…"
            onSelect={(slug) => {
              setOpen(false);
              router.push(`/champions/${slug}`);
            }}
          />
        </div>
      )}
    </div>
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
          <div className="glass-menu rounded-xl p-1.5">
            {group.items.map((it) => (
              <Link
                key={it.href}
                href={it.href}
                onClick={() => setOpen(false)}
                className="flex flex-col rounded-lg px-3 py-2 transition hover:bg-white/[0.06]"
              >
                <span className="flex items-center gap-1.5 text-sm font-medium text-text">
                  {it.label}
                  <NavBadges item={it} />
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

/* A group in the mobile drawer.
 *
 * Open by default, because the drawer's job is discovery and a tap is a wall:
 * anything folded away is effectively invisible to someone who does not
 * already know it exists. Only sections marked `collapsed` fold, and they
 * open anyway when the page you are on lives inside them, so the menu never
 * hides where you already are.
 */
function MobileGroup({
  group,
  isActive,
  onNavigate,
}: {
  group: NavGroup;
  isActive: (href: string) => boolean;
  onNavigate: () => void;
}) {
  const containsCurrent = group.items.some((it) => isActive(it.href));
  const [open, setOpen] = useState(!group.collapsed || containsCurrent);

  const links = group.items.map((it) => (
    <Link
      key={it.href}
      href={it.href}
      onClick={onNavigate}
      className={`flex items-center gap-1.5 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
        isActive(it.href) ? "text-accent bg-accent/10" : "text-muted hover:text-text hover:bg-white/[0.04]"
      }`}
    >
      {it.label}
      <NavBadges item={it} />
    </Link>
  ));

  if (!group.collapsed) {
    return (
      <div className="mt-1">
        <p className="px-3 pb-1 pt-2 text-[0.6rem] font-bold uppercase tracking-wide text-faint">
          {group.label}
        </p>
        {links}
      </div>
    );
  }

  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm font-medium text-muted transition hover:bg-white/[0.04] hover:text-text"
      >
        <span className="text-[0.6rem] font-bold uppercase tracking-wide text-faint">
          {group.label}
        </span>
        <Caret open={open} />
      </button>
      {open && links}
    </div>
  );
}

export function SiteNav({ champions }: { champions: ComboItem[] }) {
  const pathname = usePathname();
  const NAV = navEntries(useBuildToolsVisible());
  const [open, setOpen] = useState(false);

  const isActive = (href: string) => pathname === href || pathname.startsWith(href + "/");
  const groupActive = (g: NavGroup) => g.items.some((it) => isActive(it.href));

  return (
    <header className="glass-bar sticky top-0 z-50 border-b border-line">
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
                <NavBadges item={e} />
              </Link>
            ),
          )}
          <NavSearch champions={champions} />
          <span className="mx-1 h-5 w-px bg-line" />
          <DiscordNavLink />
          <SupportNavLink />
          <AccountMenu />
        </div>

        {/* mobile: the account control sits in the top bar, because signing in
            is what unlocks the extra daily generations and nobody finds an
            offer that only exists behind a hamburger. Discord gave up the slot
            for it and keeps its full entry in the drawer below. */}
        <div className="flex items-center gap-0.5 md:hidden">
          <NavSearch champions={champions} />
          <AccountMenu />
          <button
            onClick={() => setOpen((v) => !v)}
            className="grid h-10 w-10 place-items-center rounded-lg text-muted transition hover:bg-white/[0.06] hover:text-text"
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
        </div>
      </nav>

      {open && (
        <div className="glass-bar max-h-[75vh] overflow-y-auto border-t border-line px-4 py-3 md:hidden">
          <div className="flex flex-col gap-1">
            {NAV.map((e) =>
              isGroup(e) ? (
                <MobileGroup
                  key={e.label}
                  group={e}
                  isActive={isActive}
                  onNavigate={() => setOpen(false)}
                />
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
                  <NavBadges item={e} />
                </Link>
              ),
            )}
            <Link
              href={DISCORD_URL}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setOpen(false)}
              className="mt-2 flex items-center gap-2 rounded-lg bg-[#5865F2]/15 px-3 py-2.5 text-sm font-semibold text-[#98a0ff] transition hover:bg-[#5865F2]/25"
            >
              <DiscordIcon className="h-5 w-5" />
              Join our Discord
            </Link>
            <Link
              href={TIKTOK_URL}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setOpen(false)}
              className="mt-2 flex items-center gap-2 rounded-lg bg-white/[0.08] px-3 py-2.5 text-sm font-semibold text-text transition hover:bg-white/[0.14]"
            >
              <TikTokIcon className="h-5 w-5" />
              TikTok
            </Link>
            <Link
              href={YOUTUBE_URL}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setOpen(false)}
              className="mt-2 flex items-center gap-2 rounded-lg bg-[#FF0000]/15 px-3 py-2.5 text-sm font-semibold text-[#ff8a8a] transition hover:bg-[#FF0000]/25"
            >
              <YouTubeIcon className="h-5 w-5" />
              YouTube
            </Link>
            <Link
              href={BUYMEACOFFEE_URL}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setOpen(false)}
              className="mt-2 flex items-center gap-2 rounded-lg bg-[#FFDD00]/15 px-3 py-2.5 text-sm font-semibold text-gold transition hover:bg-[#FFDD00]/25"
            >
              <CoffeeIcon className="h-5 w-5" />
              Buy me a coffee
            </Link>
            <div className="mt-2">
              <AccountMenu compact />
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
