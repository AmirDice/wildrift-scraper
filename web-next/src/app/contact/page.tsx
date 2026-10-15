import type { Metadata } from "next";
import { Container, Card } from "@/components/ui";
import { ContactForm } from "@/components/contact-form";
import { DiscordButton } from "@/components/discord";

export const metadata: Metadata = {
  title: "Contact",
  description: "Report wrong data, send feedback on the build tools, or get in touch about creators and sponsorship.",
  alternates: { canonical: "/contact" },
};

export default function ContactPage() {
  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Contact</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Wrong numbers, broken pages, ideas for the build tools, or business enquiries. Every message
        is read.
      </p>
      <div className="mt-8 grid max-w-4xl gap-5 lg:grid-cols-[1fr_18rem]">
        <Card>
          <ContactForm />
        </Card>
        <Card>
          <h2 className="text-base font-semibold">Faster answers</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            The Discord is the quickest way to ask a question or report something that looks off,
            and other players often answer before we do.
          </p>
          <div className="mt-4"><DiscordButton>Join the Discord</DiscordButton></div>
          <p className="mt-4 text-xs leading-relaxed text-faint">
            What you send through the form is stored only to read and answer it. See the privacy page
            for details.
          </p>
        </Card>
      </div>
    </Container>
  );
}
