import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { DraftAssistant } from "@/components/draft-assistant";
import { Container } from "@/components/ui";
import { BUILD_TOOLS_LIVE, DRAFT_TOOL_LIVE } from "@/lib/flags";
import { buildToolsVisible } from "@/lib/access";

export const metadata: Metadata = {
  title: "Draft Assistant | Wild Rift Bans, Picks & Counter Builds",
  description:
    "A live-draft companion for Wild Rift: track all ten bans and both teams' picks, get pick suggestions from the champions you actually play, and generate the counter build for the enemy comp in one tap.",
  alternates: { canonical: "/draft" },
  robots: BUILD_TOOLS_LIVE && DRAFT_TOOL_LIVE ? undefined : { index: false, follow: false },
};

export default async function DraftPage() {
  // Held back while the draft flow is tested against real lobbies, on top of
  // the same curtain as the rest of the Build Studio tools.
  if (!DRAFT_TOOL_LIVE) redirect("/");
  if (!(await buildToolsVisible())) redirect("/");
  return (
    <Container>
      <div className="py-6">
        <h1 className="text-2xl font-bold sm:text-3xl">Draft Assistant</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Track the lobby as it happens: bans (all ten, duplicates included), their picks,
          your team. It suggests what to pick from the champions you play, and turns the
          enemy comp into a counter build with one tap.
        </p>
        {/* The highest-intent placement on the site: someone tracking a live
            draft in a browser is exactly the person who wants this on the
            phone the game is running on. */}
        <Link
          href="/overlay"
          className="glass mt-4 flex items-center gap-3 rounded-xl border border-gold/25 p-3 transition hover:border-gold/50"
        >
          <span className="rounded bg-gold/20 px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-gold">
            Soon
          </span>
          <span className="min-w-0 flex-1 text-xs text-muted">
            <span className="font-semibold text-text">This, but on top of the game.</span>{" "}
            An Android overlay that reads champion select and builds against their five without
            leaving Wild Rift.
          </span>
          <span aria-hidden className="shrink-0 text-sm text-gold">&rarr;</span>
        </Link>
        <div className="mt-5">
          <DraftAssistant />
        </div>
      </div>
    </Container>
  );
}
