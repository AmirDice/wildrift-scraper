import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { SecondScreen } from "@/components/second-screen";
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
          Mirror your phone to this computer, share that window, and the draft is read for
          you. Nothing is installed on the phone, so it works on iPhone as well as Android.
        </p>
        <ol className="mt-4 max-w-2xl list-decimal space-y-1 pl-5 text-sm text-muted">
          <li>
            Mirror your phone to this PC. iPhone: AirPlay to an AirPlay receiver. Android:
            Phone Link, Samsung DeX, or scrcpy over USB.
          </li>
          <li>
            Load the icons, then share <strong>the mirror window</strong> rather than your
            whole screen. Sharing the whole screen still works, but the phone then sits in
            the middle of a landscape frame and has to be found first.
          </li>
          <li>Open champion select. The draft appears below as it is read.</li>
        </ol>
        <div className="mt-6">
          <SecondScreen />
        </div>
      </div>
    </Container>
  );
}
