import type { Metadata } from "next";
import Link from "next/link";
import { Container } from "@/components/ui";
import { NotifyForm } from "@/components/notify-form";
import { OVERLAY_APK, OVERLAY_DOWNLOAD_LIVE, OVERLAY_VERSION } from "@/lib/flags";

export const metadata: Metadata = {
  title: "Wild Rift Draft Overlay | Counter Builds On Top Of The Game",
  description:
    "An Android overlay for Wild Rift champion select: it reads the picks off the screen, suggests what to play from your own pool, and turns the enemy five into a counter build without leaving the game.",
  alternates: { canonical: "/overlay" },
};

/** What it does, in the order someone in champion select would meet it. */
const FEATURES = [
  {
    title: "Reads champion select",
    body: "Tap watch and it takes one frame of the screen, matches the portraits against the champion icons it already has, and fills in the bans and both teams for you. Everything can still be tapped in by hand.",
  },
  {
    title: "Tells you what to pick",
    body: "Suggestions come from the champions you actually play, weighted against what they have already locked, so it does not hand you a champion you have never touched.",
  },
  {
    title: "Builds against their five",
    body: "One tap turns the enemy comp into items and runes chosen for that comp, not the generic build you would copy for every game.",
  },
  {
    title: "Reads both comps",
    body: "Names what your side is missing before it costs you the game: no frontline, no crowd control, every point of damage on the same side of the resistance split.",
  },
] as const;

const STEPS = [
  "Download the file and open it. Android will ask whether to allow installs from your browser; that prompt is normal for anything not from the Play Store.",
  "Open the app once and grant Draw over other apps. This is the permission that lets it sit on top of Wild Rift.",
  "Start a game. Pull the bar out from the edge of the screen whenever you want it, and push it back when you do not.",
  "In champion select, tap WATCH and accept the screen capture prompt if you want it to fill the picks in for you.",
] as const;

export default function OverlayPage() {
  return (
    <Container>
      <div className="py-8">
        <div className="max-w-3xl">
          <span className="inline-flex items-center gap-2 rounded-full border border-gold/30 bg-gold/10 px-3 py-1 text-[0.65rem] font-bold uppercase tracking-wide text-gold">
            In testing
          </span>
          <h1 className="mt-3 text-3xl font-bold sm:text-4xl">The draft, on top of the game</h1>
          <p className="mt-3 text-base text-muted">
            An Android overlay that sits over Wild Rift during champion select. It knows who is
            banned, who is picked and who you play, and it turns the five champions on the other
            side into a build before the loading screen is over. Nothing to alt-tab to, because
            there is nowhere to alt-tab to on a phone.
          </p>
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
          <div>
            <div className="grid gap-4 sm:grid-cols-2">
              {FEATURES.map((feature) => (
                <div key={feature.title} className="glass rounded-xl border border-white/10 p-4">
                  <h2 className="text-sm font-bold text-text">{feature.title}</h2>
                  <p className="mt-1.5 text-xs leading-relaxed text-muted">{feature.body}</p>
                </div>
              ))}
            </div>

            <div className="glass mt-4 rounded-xl border border-white/10 p-4">
              <h2 className="text-sm font-bold text-text">Make it look like yours</h2>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">
                Six frames, from a plain dark bar to a full Hextech crest, and a colour for every
                champion in the game drawn from their own splash art. Pick Hecarim and the bar
                turns Hecarim green. None of it is an image download; it is all drawn at the size
                your phone runs at, which is why the whole app is under a quarter of a megabyte.
              </p>
            </div>

            <div className="glass mt-4 rounded-xl border border-white/10 p-4">
              <h2 className="text-sm font-bold text-text">Installing it</h2>
              <ol className="mt-2 space-y-2">
                {STEPS.map((step, i) => (
                  <li key={i} className="flex gap-2.5 text-xs leading-relaxed text-muted">
                    <span className="mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-white/10 text-[0.6rem] font-bold text-text">
                      {i + 1}
                    </span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
              <p className="mt-3 border-t border-white/10 pt-3 text-[0.7rem] leading-relaxed text-faint">
                Needs Android 8.0 or newer. It never touches the game itself: it reads the same
                picture of the screen a screen recorder would, only when you ask it to, and it
                types nothing back. Everything it suggests is the same data this site publishes.
              </p>
            </div>
          </div>

          <div className="space-y-4">
            {OVERLAY_DOWNLOAD_LIVE ? (
              <div className="glass rounded-xl border border-emerald-400/30 p-4">
                <a
                  href={OVERLAY_APK}
                  download
                  className="block w-full rounded-lg bg-emerald-400 px-4 py-3 text-center text-sm font-bold text-black transition hover:brightness-110"
                >
                  Download for Android
                </a>
                <p className="mt-2 text-center text-[0.7rem] text-faint">
                  Version {OVERLAY_VERSION} · Android 8.0+ · installs from your browser
                </p>
              </div>
            ) : (
              <div className="glass rounded-xl border border-gold/25 p-4">
                <h2 className="text-sm font-bold text-text">Not out yet</h2>
                <p className="mt-1.5 text-xs leading-relaxed text-muted">
                  It is being tested against real lobbies on real phones. Leave an address and you
                  will hear the day it can be downloaded, rather than having to keep checking.
                </p>
              </div>
            )}

            <NotifyForm source="overlay" />

            <div className="glass rounded-xl border border-white/10 p-4">
              <h2 className="text-sm font-bold text-text">Use it in a browser today</h2>
              <p className="mt-1.5 text-xs leading-relaxed text-muted">
                The counter build behind the overlay is the same one the site runs. You can point
                it at an enemy team right now.
              </p>
              <Link
                href="/build?tab=counter"
                className="mt-3 inline-flex items-center gap-1 text-xs font-bold text-accent hover:underline"
              >
                Build against their team <span aria-hidden>→</span>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </Container>
  );
}
