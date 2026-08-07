import type { Metadata } from "next";
import { Container } from "@/components/ui";
import { AdminConsole } from "@/components/admin-console";

// Never indexed, never linked from the site. Everything it does is gated by
// ADMIN_TOKEN server-side; the page itself is only a form.
export const metadata: Metadata = {
  title: "Admin | WrTrueMeta",
  robots: { index: false, follow: false, nocache: true },
};

export default function AdminPage() {
  return (
    <Container className="py-10 sm:py-14">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Admin</h1>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        Pipeline operations, invite links, sponsorship tracking, hand-recorded best-player builds,
        and the creator directory.
      </p>
      <div className="mt-8">
        <AdminConsole />
      </div>
    </Container>
  );
}
