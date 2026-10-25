import type { Metadata } from "next";
import { Container, SectionHeading } from "@/components/ui";
import { BillingPanel } from "@/components/billing-panel";

export const metadata: Metadata = {
  title: "Account & Credits",
  description: "Your WrTrueMeta account, daily Build Studio allowance and build credits.",
};

export default function AccountPage() {
  return (
    <Container className="py-10 sm:py-14">
      <SectionHeading title="Your account" subtitle="Daily Build Studio allowance and build credits" />
      <div className="mt-6 max-w-4xl"><BillingPanel /></div>
    </Container>
  );
}
