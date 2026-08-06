"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { track } from "@/components/share-build";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";

/* The bottom-right flagship nudge.
 *
 * The measured problem (Top Pages, Jul 5 - Aug 4): the home page took 690
 * visitors and the tier list 498, while the two tools that make the site
 * different -- the Build Studio (258) and the counter builder (110) -- and the
 * meta overview (101) saw a fraction of that. Cross-links exist, but they sit
 * at the BOTTOM of long pages, and a visitor reading the top of the tier list
 * never reaches them. Sixty-plus champion pages arrive from search and
 * dead-end the same way.
 *
 * So: after real engagement (35s of dwell, or two thirds of the page
 * scrolled), one small card slides into the bottom-right corner and suggests
 * ONE next page. The rules that keep it from being a popup in the bad sense:
 *
 *   - one nudge per page load, at most two per session
 *   - never advertises the page you are on, or any page you have already
 *     visited this session (a suggestion to go where you have been is noise)
 *   - dismissing it silences ALL nudges for a day, not just that card
 *   - engagement-triggered, never on-load; entrance animation respects
 *     prefers-reduced-motion
 *   - shown / clicked / dismissed are counted, so whether it actually moves
 *     anyone is a number, not an opinion
 */

type Flagship = {
  path: string;
  /** A pathname prefix means "already there" -- /build covers both tools. */
  activeOn: string[];
  eyebrow: string;
  title: string;
  body: string;
  cta: string;
};

// Priority order: the biggest gap between "what makes the site different" and
// "what gets seen" first. The build tools need BUILD_TOOLS_LIVE.
const FLAGSHIPS: Flagship[] = [
  {
    path: "/build?tab=generate",
    activeOn: ["/build", "/counter"],
    eyebrow: "Build Studio",
    title: "Know what you're building next game?",
    body: "The generator reads your champion, role and playstyle and returns the optimal items, runes and summoners -- every choice explained.",
    cta: "Get my build",
  },
  {
    path: "/build?tab=counter",
    activeOn: ["/build", "/counter"],
    eyebrow: "Build vs Enemy Team",
    title: "Stuck against a comp that beats you?",
    body: "Name the five enemies and get the build that answers exactly those picks -- with what it counters and what it concedes.",
    cta: "Build against their team",
  },
  {
    path: "/meta",
    activeOn: ["/meta"],
    eyebrow: "Meta Overview",
    title: "Want the whole meta on one page?",
    body: "What the top 50 players on every champion actually build, the runes that win, and who is rising -- all from live boards.",
    cta: "See the meta",
  },
  {
    path: "/tier-list",
    activeOn: ["/tier-list"],
    eyebrow: "Tier List",
    title: "Wondering who is actually strong right now?",
    body: "Every champion ranked by the real win rates of their best players -- EU and CN, filterable by role.",
    cta: "Open the tier list",
  },
];

const DAY_MS = 24 * 60 * 60 * 1000;
const DWELL_MS = 35_000;
const SCROLL_FRACTION = 0.66;
const SESSION_CAP = 2;

/** localStorage/sessionStorage access that never throws (private mode). */
function store(kind: "local" | "session"): Storage | null {
  try {
    return kind === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

function pickFlagship(pathname: string): Flagship | null {
  const session = store("session");
  const visited: string[] = JSON.parse(session?.getItem("wtm_visited") ?? "[]");
  for (const f of FLAGSHIPS) {
    if (!BUILD_TOOLS_LIVE && f.path.startsWith("/build")) continue;
    if (f.activeOn.some((p) => pathname.startsWith(p))) continue;
    if (visited.some((v) => f.activeOn.some((p) => v.startsWith(p)))) continue;
    return f;
  }
  return null;
}

export function FlagshipNudge() {
  const pathname = usePathname();
  const [flagship, setFlagship] = useState<Flagship | null>(null);
  const [visible, setVisible] = useState(false);
  const fired = useRef(false);

  useEffect(() => {
    // Remember where this session has been, BEFORE deciding what to offer.
    const session = store("session");
    if (session) {
      const visited: string[] = JSON.parse(session.getItem("wtm_visited") ?? "[]");
      if (!visited.includes(pathname)) {
        session.setItem("wtm_visited", JSON.stringify([...visited, pathname].slice(-40)));
      }
    }

    fired.current = false;
    setVisible(false);
    setFlagship(null);

    const local = store("local");
    const silencedAt = Number(local?.getItem("wtm_nudge_silenced") ?? 0);
    if (silencedAt && Date.now() - silencedAt < DAY_MS) return;
    const shown = Number(session?.getItem("wtm_nudge_count") ?? 0);
    if (shown >= SESSION_CAP) return;

    const target = pickFlagship(pathname);
    if (!target) return;

    const fire = () => {
      if (fired.current) return;
      fired.current = true;
      setFlagship(target);
      setVisible(true);
      session?.setItem("wtm_nudge_count", String(shown + 1));
      track("nudge_shown");
    };

    const timer = window.setTimeout(fire, DWELL_MS);
    const onScroll = () => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      if (max > 400 && window.scrollY / max >= SCROLL_FRACTION) fire();
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("scroll", onScroll);
    };
  }, [pathname]);

  if (!flagship || !visible) return null;

  return (
    <div
      role="complementary"
      aria-label="Suggested page"
      className="fixed bottom-4 right-4 z-40 w-[min(21rem,calc(100vw-2rem))] motion-safe:animate-[nudge-in_0.35s_ease-out]"
    >
      <div className="liquid-glass rounded-2xl p-4">
        <div className="flex items-start justify-between gap-2">
          <p className="text-[0.65rem] font-bold uppercase tracking-wide text-accent">
            {flagship.eyebrow}
          </p>
          <button
            type="button"
            aria-label="Dismiss suggestion"
            onClick={() => {
              setVisible(false);
              store("local")?.setItem("wtm_nudge_silenced", String(Date.now()));
              track("nudge_dismissed");
            }}
            className="-m-1 rounded p-1 leading-none text-faint transition hover:text-text"
          >
            ✕
          </button>
        </div>
        <p className="mt-1 text-sm font-semibold text-text">{flagship.title}</p>
        <p className="mt-1 text-xs leading-relaxed text-muted">{flagship.body}</p>
        <Link
          href={flagship.path}
          onClick={() => {
            setVisible(false);
            track("nudge_clicked");
          }}
          className="mt-3 inline-flex items-center gap-1 rounded-lg bg-accent px-3 py-1.5 text-xs font-bold text-[#07121f] transition hover:brightness-110"
        >
          {flagship.cta} <span aria-hidden>→</span>
        </Link>
      </div>
    </div>
  );
}
