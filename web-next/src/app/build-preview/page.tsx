import type { Metadata } from "next";
import { BuildStudio } from "@/components/build-studio";
import { Container } from "@/components/ui";

// Build optimizer review page (clean, mobile-first, one champion at a time).
// Not linked in nav/sitemap; noindex until the full roster is generated.
export const metadata: Metadata = {
  title: "Build Optimizer | WrTrueMeta",
  robots: { index: false, follow: false },
};

export default function BuildPreviewPage() {
  return (
    <Container className="py-8">
      <div className="mb-1 flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Build Optimizer</h1>
        <span className="rounded-md bg-accent/20 px-2 py-1 text-[0.65rem] font-bold uppercase tracking-wide text-accent">
          Preview
        </span>
      </div>
      <p className="mb-6 max-w-xl text-sm text-muted">
        Engine-optimized builds for every champion. Pick your champion, switch playstyles,
        customize, and counter the enemy team.
      </p>
      <BuildStudio />
    </Container>
  );
}
