import type { Metadata } from "next";
import "./globals.css";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import { Analytics } from "@vercel/analytics/next";

export const metadata: Metadata = {
  metadataBase: new URL("https://wrtruemeta.com"),
  title: {
    default: "WrTrueMeta — Wildrift Tier List, Win Rates & Meta Tracker",
    template: "%s | WrTrueMeta",
  },
  description:
    "Real League of Legends Wildrift win rates from the top 50 players on every champion. Tier list, leaderboards, best players, role & class meta — updated twice a month.",
  keywords: [
    "Wildrift tier list",
    "Wild Rift tier list",
    "League of Legends Wildrift",
    "Wildrift meta",
    "Wildrift win rates",
    "Wildrift champions",
  ],
  openGraph: {
    type: "website",
    siteName: "WrTrueMeta",
    url: "https://wrtruemeta.com",
    title: "WrTrueMeta — Wildrift Tier List, Win Rates & Meta Tracker",
    description:
      "Real League of Legends Wildrift win rates from the top 50 players on every champion.",
  },
  twitter: {
    card: "summary_large_image",
    title: "WrTrueMeta — Wildrift Tier List & Meta Tracker",
    description:
      "Real Wildrift win rates from the top 50 players of every champion.",
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full">
      <body className="flex min-h-full flex-col">
        {/* Ambient fixed background — dimmed Ionia art gives the frosted glass
            something to refract without overpowering the minimal dark theme. */}
        <div
          aria-hidden
          className="fixed inset-0 -z-20 bg-cover bg-center"
          style={{ backgroundImage: "url(/ionia.jpg)" }}
        />
        <div
          aria-hidden
          className="fixed inset-0 -z-10"
          style={{
            background:
              "linear-gradient(180deg, rgba(7,10,18,0.84), rgba(7,10,18,0.94)), radial-gradient(70% 55% at 50% 0%, rgba(79,141,255,0.12), transparent 70%)",
          }}
        />
        <SiteNav />
        <main className="flex-1">{children}</main>
        <SiteFooter />
        <Analytics />
      </body>
    </html>
  );
}
