import type { Metadata } from "next";
import { Container, SectionHeading } from "@/components/ui";
import { BillingPanel } from "@/components/billing-panel";

export const metadata: Metadata = {
  title: "Account & WRTrueMeta Plus",
  description: "Manage your WrTrueMeta account and Build Studio subscription.",
};

export default function AccountPage() {
  return (
    <Container className="py-10 sm:py-14">
      <SectionHeading title="Your account" subtitle="Build Studio access and subscription settings" />
      <div className="mt-6 max-w-4xl"><BillingPanel /></div>
    </Container>
  );
}
