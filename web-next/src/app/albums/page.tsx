import type { Metadata } from "next";
import { Container } from "@/components/ui";
import { AlbumsView } from "@/components/albums-view";
import { StartBlend } from "@/components/start-blend";

export const metadata: Metadata = {
  title: "Build Albums | WrTrueMeta",
  description:
    "Collect your Wild Rift builds into albums: your one-tricks, your climbing picks, the builds you want to try next patch. Then blend albums with a friend.",
  alternates: { canonical: "/albums" },
  robots: { index: true, follow: true },
};

export default function AlbumsPage() {
  return (
    <Container className="py-10 sm:py-14">
      <div className="max-w-2xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">Your builds</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Build Albums</h1>
        <p className="mt-3 leading-relaxed text-muted">
          A build you generated once and closed is a build you lost. Albums keep them: one for your
          one-tricks, one for the role you are learning, one for the picks you want to try next patch.
        </p>
      </div>

      <div className="mt-8">
        <AlbumsView />
      </div>

      <div className="mt-10">
        <StartBlend />
      </div>
    </Container>
  );
}
