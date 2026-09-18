import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { SecondScreenReader } from "@/components/second-screen-reader";
import { SecondScreenGuide } from "@/components/second-screen-guide";
import { Container } from "@/components/ui";
import { DRAFT_TOOL_LIVE } from "@/lib/flags";

export const metadata: Metadata = {
  title: "PC Second Screen | Wild Rift Draft Assistant",
  description:
    "Mirror your phone to your PC and let the draft assistant read champion select for you. Nothing to install on the phone, and it works with iPhone.",
  alternates: { canonical: "/second-screen" },
  robots: { index: false, follow: false },
};

export default function SecondScreenPage() {
  // Behind the same curtain as the Draft Assistant it feeds, and additionally
  // unfinished: the reader is validated against calibration frames but has
  // never seen a live mirror.
  if (!DRAFT_TOOL_LIVE) redirect("/");
  return (
    <Container>
      <div className="py-6">
        <h1 className="text-2xl font-bold sm:text-3xl">PC Second Screen</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted">
          Screenshot champion select and drop it here: the draft is read off the picture.
          Nothing to install, on iPhone or Android, and it works on the phone itself.
        </p>
        {/* Every route to getting a phone screen in front of the reader, with
            the visitor's own opened for them. The old three-line list assumed
            one setup (mirror, share, read) and left everyone else guessing. */}
        <div className="mt-5">
          <SecondScreenGuide />
        </div>
        {/* The whole draft assistant, reading instead of tapping: same board,
            same suggestions, same counter build. Keeping a second readout here
            meant maintaining two front ends for one draft. */}
        <div className="mt-6">
          <SecondScreenReader />
        </div>
      </div>
    </Container>
  );
}
