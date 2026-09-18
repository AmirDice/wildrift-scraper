import type { Metadata } from "next";
import Link from "next/link";
import { Container, Card } from "@/components/ui";
import { ADSENSE_CLIENT, ADS_LIVE } from "@/lib/ads";

export const metadata: Metadata = {
  title: "Privacy & Ads | WrTrueMeta",
  description:
    "What WrTrueMeta stores, what it does not, and how advertising, analytics and Google sign-in work on the site.",
  alternates: { canonical: "/privacy" },
};

/**
 * The page ads require.
 *
 * Every ad network's terms ask for a policy that names the third parties, says
 * cookies are involved and points at the opt-outs, and the site had no such
 * page. It is written from what the code actually does rather than from a
 * generator, so it stays true: the quota is keyed on a hashed IP, sign-in is
 * optional and Google's, analytics is Vercel's, and the ad network is named
 * only while one is configured.
 */
export default function PrivacyPage() {
  const network = ADS_LIVE && ADSENSE_CLIENT;
  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Privacy and ads</h1>
      <p className="mt-2 max-w-2xl text-muted">
        What the site stores, what it does not, and who else is involved when you use it.
      </p>

      <div className="mt-8 flex max-w-3xl flex-col gap-5">
        <Card>
          <h2 className="text-lg font-semibold">The short version</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            There is no account required to use anything on the site, and nothing here is sold.
            What is stored is the minimum that makes the tools work: a hashed form of your IP
            address to count your daily build generations, the builds you choose to save, and
            anonymous page analytics. Advertising is the one place where a third party sets its
            own cookies, and that is described below.
          </p>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold">Advertising</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            The site carries display advertising and, while a build is generating, a short video
            ad capped at twenty seconds. Ads pay for the model calls behind the build generator
            and the servers the data collection runs on.
          </p>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            {network ? "Ads are served by Google" : "When advertising is enabled it will be served by Google"}
            , which may set or read cookies and similar identifiers on your device to choose ads,
            measure them and limit how often you see the same one. Google explains that use, and
            how to control it, in{" "}
            <a
              href="https://policies.google.com/technologies/partner-sites"
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-accent transition hover:opacity-80"
            >
              how Google uses information from sites that use its services
            </a>
            . You can turn personalised advertising off entirely at{" "}
            <a
              href="https://myadcenter.google.com/"
              target="_blank"
              rel="noopener noreferrer"
              className="font-medium text-accent transition hover:opacity-80"
            >
              My Ad Center
            </a>
            .
          </p>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            In the EEA, the UK and Switzerland you are asked for consent before any personalised
            ad is served, through Google&rsquo;s own consent message. Declining does not change
            what the site does for you: every tool works the same either way.
          </p>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Ads never appear on the draft assistant or the second screen. Those are used with a
            live champion select on the clock, and an ad there would cost you a pick.
          </p>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold">Build generation</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Generating a build sends your champion, role and chosen settings, plus the enemy or
            ally champions you selected, to our own server and from there to the language model
            that reasons about the build. No personal data is attached to that request. Generated
            builds are cached by the settings that produced them, so the same request can be
            answered without paying for it twice, and a cached build contains nothing about who
            asked for it.
          </p>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            The daily generation limit is enforced against a hashed, truncated form of your IP
            address. It is a counter, not a profile, and it resets every day.
          </p>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold">Signing in, and what you save</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Signing in is optional and uses Google. If you do, we store your Google account
            identifier and email so your saved builds and albums come back to you, and a session
            cookie so you stay signed in. Sign out and the cookie is gone; ask in the Discord and
            the record is deleted.
          </p>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold">Analytics</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Page views and a small number of product events (which tool was opened, whether a
            generation finished) are recorded through Vercel Analytics, which does not use cookies
            and does not identify individual visitors. It tells us which tools are worth working
            on and nothing else.
          </p>
        </Card>

        <Card>
          <h2 className="text-lg font-semibold">Your data, and getting in touch</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            You can ask what is stored about you, ask for it to be deleted, or object to
            advertising cookies. The fastest route is a message in{" "}
            <Link href="/creators" className="font-medium text-accent transition hover:opacity-80">
              the Discord
            </Link>
            , or a DM to @generalthr4gg. Clearing your browser&rsquo;s site data for wrtruemeta.com
            removes everything stored locally, including the ad consent choice and any saved
            preferences.
          </p>
          <p className="mt-3 text-xs text-faint">
            WrTrueMeta is not affiliated with Riot Games. League of Legends and Wild Rift are
            &copy; Riot Games, Inc.
          </p>
        </Card>
      </div>
    </Container>
  );
}
