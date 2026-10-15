import type { Metadata } from "next";
import Link from "next/link";
import { Container, Card } from "@/components/ui";
import { NotifyForm } from "@/components/notify-form";
import {
  CHANGELOG,
  CN_WINRATE_PATCH,
  COLLECTION_EXPECTED_FINISH,
  COLLECTION_IN_PROGRESS,
  COLLECTION_PENDING_REGIONS,
  COLLECTION_REGIONS,
  COLLECTION_START,
  EU_WINRATE_PATCH,
  NA_WINRATE_PATCH,
  SKIPPED_PATCH,
} from "@/lib/announcement";
import site from "@/data/site.json";
import siteNa from "@/data/site_na.json";
import siteCn from "@/data/site_cn.json";

export const metadata: Metadata = {
  title: COLLECTION_IN_PROGRESS
    ? `Site Updates | ${COLLECTION_REGIONS} Data Collection In Progress`
    : `Site Updates | Patch ${SKIPPED_PATCH} Is Live`,
  description: COLLECTION_IN_PROGRESS
    ? `${COLLECTION_REGIONS} ladder data collection is underway and is expected to finish ${COLLECTION_EXPECTED_FINISH}. Each region publishes as its pass completes.`
    : `Ability, item and rune data is on patch ${SKIPPED_PATCH}. Win rates are the ${CN_WINRATE_PATCH} boards for EU, NA and China until the next collection.`,
  alternates: { canonical: "/updates" },
};

const EU_COLLECTED = (site as { collectedOn?: string }).collectedOn ?? null;
const NA_COLLECTED = (siteNa as { collectedOn?: string }).collectedOn ?? null;
const CN_COLLECTED = (siteCn as { collectedOn?: string }).collectedOn ?? null;

export default function UpdatesPage() {
  return (
    <Container className="py-12 sm:py-16">
      <div className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
          Site update
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
          {COLLECTION_IN_PROGRESS
            ? `${COLLECTION_REGIONS} data collection is underway.`
            : `Patch ${SKIPPED_PATCH} is live.`}
        </h1>
        <p className="mt-4 text-lg leading-relaxed text-muted">
          {/* Built as one string rather than interleaved JSX text and
              expressions: the compiler dropped the space between
              {SKIPPED_PATCH} and the word after it, rendering "7.2echanged"
              on the live page. Prose with several interpolations is not worth
              debugging one {" "} at a time. */}
          {`Every ability, item and rune number on the site is on patch ${SKIPPED_PATCH}. `
            + `The win rates are not, and cannot be until the ladders are collected again: `
            + `NA was collected on 6 October, EU on 7 October and China on 11 October, `
            + `142 champions each, all played on patch ${NA_WINRATE_PATCH}. So a champion `
            + `${SKIPPED_PATCH} changed still shows how it performed before the change.`}
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
                <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-emerald-300">
                  Measured on {EU_WINRATE_PATCH}
                </p>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">
                  {`Win rates, tiers, pick rates and movement change only when a region's `
                    + `leaderboards are re-scraped. All three boards were collected on `
                    + `${EU_WINRATE_PATCH}, so Volibear, Jhin, Tryndamere, Hwei, Nocturne, `
                    + `Yunara, Senna and Yasuo show their ${EU_WINRATE_PATCH} results until the `
                    + `next collection, not how ${SKIPPED_PATCH} has moved them.`}
                </p>
              </div>
            </div>
            <dl className="mt-4 grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
                <dt className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">
                  Europe, collected
                </dt>
                <dd className="mt-1 text-sm font-semibold text-text">
                  {EU_COLLECTED ?? "Current dataset"}
                </dd>
                <dd className="mt-0.5 text-xs text-muted">
                  All 142 champions, played on {EU_WINRATE_PATCH}.
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
                  All 142 champions, played on {NA_WINRATE_PATCH}.
                </dd>
              </div>
              <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3">
                <dt className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">
                  China, collected
                </dt>
                <dd className="mt-1 text-sm font-semibold text-text">
                  {CN_COLLECTED ?? "Current dataset"}
                </dd>
                <dd className="mt-0.5 text-xs text-muted">
                  All 142 champions, played on {CN_WINRATE_PATCH}.
                </dd>
              </div>
            </dl>
            <p className="mt-4 text-sm leading-relaxed text-muted">
              Tencent&apos;s own China bracket rates are separate from these boards. They refresh
              daily and follow their own cycle, so they keep moving as normal.
            </p>
          </Card>

          {COLLECTION_IN_PROGRESS && (
          <Card className="p-5">
            <h2 className="text-base font-semibold text-text">Why the collection takes until Wednesday</h2>
            <p className="mt-2.5 text-sm leading-relaxed text-muted">
              A collection is a full scrape of the top of the ladder for every champion across
              three regions. It runs in sequence so the phone session remains reliable, which is
              why the window runs from {COLLECTION_START} through {COLLECTION_EXPECTED_FINISH}.
              Each region is published as soon as its pass is complete, and the bar under the
              menu shows how far each one has got.
            </p>
          </Card>
          )}

          <Card className="p-5">
            <h2 className="text-base font-semibold text-text">
              {COLLECTION_IN_PROGRESS ? "What happens during the window" : "Where the patch shows up"}
            </h2>
            <p className="mt-2.5 text-sm leading-relaxed text-muted">
              {COLLECTION_IN_PROGRESS
                ? `The scraper is collecting champion win rates and the most-built player builds for `
                  + `${COLLECTION_REGIONS}. Patch ${SKIPPED_PATCH} item and ability data is already used `
                  + `by the Build Studio, Counter Builder, Draft Assistant and champion pages; this run `
                  + `refreshes the empirical ladder layer those tools reference.`
                : `Patch ${SKIPPED_PATCH} item, rune and ability data is what the Build Studio, Counter `
                  + `Builder, Draft Assistant and champion pages calculate from, so every build and `
                  + `damage figure generated from today uses it. Builds cached before the patch were `
                  + `retired rather than served.`}
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

          <Card className="p-5">
            <h2 className="text-base font-semibold text-text">What changed, and when</h2>
            <p className="mt-2.5 text-sm leading-relaxed text-muted">
              Corrections to the numbers are listed here rather than shipped quietly.
              If a figure you remember has moved, this is why.
            </p>
            <ol className="mt-4 space-y-4">
              {CHANGELOG.map((entry) => (
                <li
                  key={`${entry.date}-${entry.title}`}
                  className="border-l-2 border-white/12 pl-4"
                >
                  <p className="text-[0.65rem] font-semibold uppercase tracking-wide text-faint">
                    {entry.date}
                  </p>
                  <p className="mt-0.5 text-sm font-semibold text-text">{entry.title}</p>
                  <p className="mt-1 text-sm leading-relaxed text-muted">{entry.body}</p>
                </li>
              ))}
            </ol>
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
