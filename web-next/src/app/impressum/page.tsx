import type { Metadata } from "next";
import Link from "next/link";
import { Container, Card } from "@/components/ui";
import { impressum, impressumComplete } from "@/lib/impressum";

export const metadata: Metadata = {
  title: "Impressum",
  description: "Operator details for WrTrueMeta as required by German law.",
  alternates: { canonical: "/impressum" },
  robots: { index: true, follow: true },
};

/** Operator details (section 5 DDG). The values live in the environment, see lib/impressum.ts. */
export default function ImpressumPage() {
  const i = impressum();
  const complete = impressumComplete();
  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Impressum</h1>
      <p className="mt-2 max-w-2xl text-muted">Information according to section 5 DDG (Digitale-Dienste-Gesetz).</p>
      <div className="mt-8 flex max-w-3xl flex-col gap-5">
        {complete ? (
          <>
            <Card className="p-5 sm:p-6">
              <h2 className="text-lg font-semibold">Operator</h2>
              <address className="mt-2 text-sm not-italic leading-relaxed text-muted">
                {i.name}<br />
                WrTrueMeta<br />
                {i.street}<br />
                {i.city}<br />
                {i.country}
              </address>
            </Card>
            <Card className="p-5 sm:p-6">
              <h2 className="text-lg font-semibold">Contact</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                Email: <a href={`mailto:${i.email}`} className="font-medium text-accent hover:opacity-80">{i.email}</a>
                <br />
                Or use the <Link href="/contact" className="font-medium text-accent hover:opacity-80">contact form</Link>.
              </p>
            </Card>
            {(i.vatId || i.smallBusiness) && (
              <Card className="p-5 sm:p-6">
                <h2 className="text-lg font-semibold">VAT</h2>
                <p className="mt-2 text-sm leading-relaxed text-muted">
                  {i.vatId
                    ? <>VAT identification number according to section 27a UStG: {i.vatId}</>
                    : <>As a small business under section 19 UStG, no VAT is charged or shown.</>}
                </p>
              </Card>
            )}
            <Card className="p-5 sm:p-6">
              <h2 className="text-lg font-semibold">Responsible for content</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                Responsible for the content according to section 18 (2) MStV: {i.name}, address as above.
              </p>
            </Card>
            <Card className="p-5 sm:p-6">
              <h2 className="text-lg font-semibold">Online dispute resolution</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                We are not obliged and not willing to take part in dispute resolution proceedings before a
                consumer arbitration board.
              </p>
            </Card>
          </>
        ) : (
          <Card className="p-5 sm:p-6">
            <p className="text-sm leading-relaxed text-muted">
              Operator details are being added. Until then, please reach us through the{" "}
              <Link href="/contact" className="font-medium text-accent hover:opacity-80">contact form</Link>.
            </p>
          </Card>
        )}
      </div>
    </Container>
  );
}
