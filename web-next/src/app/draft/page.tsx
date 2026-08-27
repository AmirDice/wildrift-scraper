import type { Metadata } from "next";
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
        <div className="mt-5">
          <DraftAssistant />
        </div>
      </div>
    </Container>
  );
}
