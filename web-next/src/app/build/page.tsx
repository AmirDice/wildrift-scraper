import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { BuildStudio } from "@/components/build-studio";
import { Container } from "@/components/ui";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";

export const metadata: Metadata = {
  title: "Build Optimizer | Wild Rift Builds, Runes & Item Order",
  description:
    "Optimized Wild Rift builds for every champion: pick your champion, switch playstyles, customize items and runes, or generate a build tuned to your exact game.",
  alternates: { canonical: "/build" },
  robots: BUILD_TOOLS_LIVE ? undefined : { index: false, follow: false },
};

export default function BuildPage() {
  if (!BUILD_TOOLS_LIVE) redirect("/");
  return (
    <Container className="py-8">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Build Optimizer</h1>
      <p className="mb-6 mt-1 max-w-xl text-sm text-muted">
        Optimized builds for every champion. Pick your champion, switch playstyles,
        customize items and runes, or generate a build tuned to your exact game.
      </p>
      <BuildStudio />
    </Container>
  );
}
