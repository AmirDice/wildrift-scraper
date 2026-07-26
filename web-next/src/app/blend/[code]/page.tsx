import type { Metadata } from "next";
import { Container } from "@/components/ui";
import { BlendView } from "@/components/blend-view";

export const metadata: Metadata = {
  title: "Duo Blend | WrTrueMeta",
  description: "Two players' Wild Rift build albums, mixed: shared picks, taste match and a duo queue list.",
  robots: { index: false, follow: false },
};

export default async function BlendPage(props: PageProps<"/blend/[code]">) {
  const { code } = await props.params;
  return (
    <Container className="py-10 sm:py-14">
      <div className="mb-8 max-w-2xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">Duo Blend</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
          What you two actually play
        </h1>
        <p className="mt-3 leading-relaxed text-muted">
          Two build albums, mixed. How much taste you share, the champions you both saved, and a pick
          list for the next time you queue together.
        </p>
      </div>
      <BlendView code={code} />
    </Container>
  );
}
