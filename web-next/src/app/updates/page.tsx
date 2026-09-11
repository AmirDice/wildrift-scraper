import type { Metadata } from "next";
import Link from "next/link";
import { Container, Card } from "@/components/ui";
import { NotifyForm } from "@/components/notify-form";
import { NEXT_PATCH, SKIPPED_PATCH, WINRATE_PATCH } from "@/lib/announcement";
import site from "@/data/site.json";
import siteNa from "@/data/site_na.json";

export const metadata: Metadata = {
  title: `Site Updates | Patch ${SKIPPED_PATCH} Applied, Win Rates Held for ${NEXT_PATCH}`,
  description:
    `Patch ${SKIPPED_PATCH} item and ability changes are live on WrTrueMeta. Win rates stay on the ${WINRATE_PATCH} boards until ${NEXT_PATCH}. Get an email when the numbers move or something new ships.`,
  alternates: { canonical: "/updates" },
};

const EU_COLLECTED = (site as { collectedOn?: string }).collectedOn ?? null;
const NA_COLLECTED = (siteNa as { collectedOn?: string }).collectedOn ?? null;

export default function UpdatesPage() {
  return (
    <Container className="py-12 sm:py-16">
      <div className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
          Site update
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
          Patch {SKIPPED_PATCH} is applied. Win rates are not being re-collected.
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          {/* Built as one string rather than interleaved JSX text and
              expressions: the compiler dropped the space between
              {SKIPPED_PATCH} and the word after it, rendering "7.2echanged"
              on the live page. Prose with several interpolations is not worth
              debugging one {" "} at a time. */}
          {`Everything patch ${SKIPPED_PATCH} changed directly is already on the site: `
            + `Vi, Swain, Janna, Nautilus and Malphite, plus Eclipse, Unending Despair `
            + `and Seeker’s Armguard. What is not happening is a fresh scrape of the `
            + `ladder. The win rates stay on the ${WINRATE_PATCH} boards, the next `
            + `collection will be for patch ${NEXT_PATCH}, and the time that frees up is `
            + `going into new features.`}
        </p>
      </div>

      <div className="mt-10 grid gap-5 lg:grid-cols-[1.6fr_1fr] lg:items-start">
        <div className="space-y-5">
          <Card className="p-5">
            <h2 className="text-base font-semibold text-text">
              What is on {SKIPPED_PATCH} and what is not
            </h2>
            <div className="mt-3 space-y-3">
              <div className="rounded-xl border border-emerald-400/25 bg-emerald-400/[0.06] px-4 py-3">
                <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-emerald-300">
                  Updated to {SKIPPED_PATCH}
                </p>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">
                  Ability ratios, cooldowns and base stats. Item stats, costs and passives.
                  Everything the Build Studio, the Counter Builder, the Draft Assistant and the
                  item and ability pages calculate from.
                </p>
              </div>
              <div className="rounded-xl border border-gold/30 bg-gold/[0.07] px-4 py-3">
                <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-gold">
                  Still measured on {WINRATE_PATCH}
                </p>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">
                  Win rates, tiers, pick rates and movement. These only change when the
                  leaderboards are re-scraped, and that is the run being skipped. A champion
                  changed by {SKIPPED_PATCH} is still showing how it performed before the patch.
                </p>
              </div>
            </div>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
                <dt className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">
                  Europe, collected
                </dt>
                <dd className="mt-1 text-sm font-semibold text-text">
                  {EU_COLLECTED ?? "Current dataset"}
                </dd>
                <dd className="mt-0.5 text-xs text-muted">
                  A full roster, played on {WINRATE_PATCH}.
                </dd>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
                <dt className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">
                  North America, collected
                </dt>
                <dd className="mt-1 text-sm font-semibold text-text">
                  {NA_COLLECTED ?? "Current dataset"}
                </dd>
                <dd className="mt-0.5 text-xs text-muted">
                  Held here until {NEXT_PATCH}.
                </dd>
              </div>
            </dl>
            <p className="mt-4 text-sm leading-relaxed text-muted">
              China is unaffected. Those figures come from Tencent, refresh daily and follow
              their own patch cycle, so they keep moving as normal.
            </p>
          </Card>

          <Card className="p-5">
            <h2 className="text-base font-semibold text-text">Why skip the collection</h2>
            <p className="mt-2.5 text-sm leading-relaxed text-muted">
              A collection is a full scrape of the top of the ladder for every champion, and it
              is the most expensive thing this site does. Running one for {SKIPPED_PATCH} would
              produce a board that {NEXT_PATCH} replaces within weeks, and it would cost the
              whole window in which the tools can actually be improved. Given the choice between
              one more set of numbers and a better site to read them on, we are taking the
              better site.
            </p>
          </Card>

          <Card className="p-5">
            <h2 className="text-base font-semibold text-text">What is being built instead</h2>
            <p className="mt-2.5 text-sm leading-relaxed text-muted">
              Work between now and {NEXT_PATCH} is going into the build and draft tools rather
              than the data pipeline: the fight engine behind the Build Studio and the Counter
              Builder, the draft assistant, and the overlay. When {NEXT_PATCH} lands, the item
              and ability data is updated first, exactly as it was for {SKIPPED_PATCH}, and the
              boards are collected once enough games have been played on it to be worth
              measuring.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link
                href="/build"
                className="inline-flex items-center gap-1 rounded-lg border border-white/12 px-3 py-1.5 text-xs font-semibold text-text transition hover:bg-white/5"
              >
                Build Studio
              </Link>
              <Link
                href="/champion-changes"
                className="inline-flex items-center gap-1 rounded-lg border border-white/12 px-3 py-1.5 text-xs font-semibold text-text transition hover:bg-white/5"
              >
                What {SKIPPED_PATCH} changed
              </Link>
              <Link
                href="/methodology"
                className="inline-flex items-center gap-1 rounded-lg border border-white/12 px-3 py-1.5 text-xs font-semibold text-text transition hover:bg-white/5"
              >
                How the data is collected
              </Link>
            </div>
          </Card>
        </div>

        <div className="space-y-4 lg:sticky lg:top-24">
          <div>
            <h2 className="text-base font-semibold text-text">Get told, instead of checking</h2>
            <p className="mt-1.5 text-sm leading-relaxed text-muted">
              Leave an address and you will hear when the win rates are re-collected and when
              something new ships. Two separate lists, so you can take one and not the other.
            </p>
          </div>
          <NotifyForm source="updates" />
          <p className="text-[0.7rem] leading-relaxed text-faint">
            Nothing else is sent, the address is not passed on, and every email carries a way
            out of the list.
          </p>
        </div>
      </div>
    </Container>
  );
}
