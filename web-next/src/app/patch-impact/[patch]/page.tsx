import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, Container } from "@/components/ui";
import { JsonLd, breadcrumbJsonLd } from "@/lib/structured-data";
import { AdSlot } from "@/components/ad-slot";
import { getPatchImpact, impactPatches, LANE_NAME, type ImpactEntry } from "@/lib/patch-impact";

/* eslint-disable @next/next/no-img-element */

/**
 * What one patch did to China's Legendary builds: every item and rune the
 * patch notes touched, before and after, by role, with the lanes that moved
 * most, plus what shifted without being touched and how the changed
 * champions' win rates went.
 */
export function generateStaticParams() {
  return impactPatches().map((patch) => ({ patch }));
}

export async function generateMetadata(props: PageProps<"/patch-impact/[patch]">): Promise<Metadata> {
  const { patch } = await props.params;
  const data = getPatchImpact(patch);
  if (!data) return {};
  const lead = data.changedItems[0];
  return {
    title: `Patch ${patch} Impact on Builds | What Changed in China's Wild Rift Meta`,
    description: `How Wild Rift patch ${patch} moved China's Legendary builds: every changed item and rune before and after, by role${lead ? `, from ${lead.name} (${lead.before.toFixed(1)}% to ${lead.after.toFixed(1)}%)` : ""} to the champions it buffed and nerfed.`,
    alternates: { canonical: `/patch-impact/${patch}` },
  };
}

const ROLE_ORDER = ["baron", "jungle", "mid", "dragon", "support"];

function Delta({ before, after }: { before: number; after: number }) {
  const d = Math.round((after - before) * 10) / 10;
  return (
    <span className={`tabular-nums ${d > 0.2 ? "text-emerald-300" : d < -0.2 ? "text-rose-300" : "text-muted"}`}>
      {`${before.toFixed(1)}% → ${after.toFixed(1)}%`}
    </span>
  );
}

function EntryCard({ entry, kind }: { entry: ImpactEntry; kind: "item" | "rune" }) {
  const roles = ROLE_ORDER.filter((role) => entry.roles[role] && Math.max(entry.roles[role].before, entry.roles[role].after) >= 0.5);
  const max = Math.max(1, ...roles.flatMap((role) => [entry.roles[role].before, entry.roles[role].after]));
  return (
    <Card className="p-5">
      <div className="flex items-start gap-3">
        <img src={entry.icon} alt="" className="h-12 w-12 shrink-0 rounded-xl border border-white/10 bg-black/25" loading="lazy" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-base font-semibold">{entry.href ? <Link href={entry.href} className="hover:text-accent">{entry.name}</Link> : entry.name}</h3>
            <span className="text-sm font-semibold"><Delta before={entry.before} after={entry.after} /></span>
          </div>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">{entry.summary}</p>
        </div>
      </div>
      {roles.length > 0 && (
        <div className="mt-4 space-y-1.5">
          {roles.map((role) => (
            <div key={role} className="grid grid-cols-[4.5rem_1fr_7rem] items-center gap-2 text-xs">
              <span className="text-faint">{LANE_NAME[role]}</span>
              <span className="relative h-2 overflow-hidden rounded-full bg-white/[0.06]">
                <span className="absolute inset-y-0 left-0 rounded-full bg-white/25" style={{ width: `${(entry.roles[role].before / max) * 100}%` }} />
                <span className="absolute inset-y-0 left-0 rounded-full bg-sky-300/80" style={{ width: `${(entry.roles[role].after / max) * 100}%`, height: "50%", top: "25%" }} />
              </span>
              <span className="text-right"><Delta before={entry.roles[role].before} after={entry.roles[role].after} /></span>
            </div>
          ))}
          <p className="pt-1 text-[0.65rem] text-faint">{`Grey: before the patch. Blue: after. Share of each role's ${kind === "item" ? "cores" : "rune pages"}.`}</p>
        </div>
      )}
      {entry.movers.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {entry.movers.slice(0, 4).map((m) => (
            <Link key={`${m.slug}-${m.lane}`} href={`/champions/${m.slug}`}
              className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-black/15 px-2 py-1 text-xs hover:border-accent/30">
              <img src={m.icon} alt="" className="h-5 w-5 rounded-full" loading="lazy" />
              <span>{`${m.champion} ${LANE_NAME[m.lane] ?? m.lane}`}</span>
              <Delta before={m.before} after={m.after} />
            </Link>
          ))}
        </div>
      )}
    </Card>
  );
}

export default async function PatchImpactPage(props: PageProps<"/patch-impact/[patch]">) {
  const { patch } = await props.params;
  const data = getPatchImpact(patch);
  if (!data) notFound();
  const live = data.liveDate ? new Date(`${data.liveDate}T00:00:00Z`).toLocaleDateString("en", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }) : null;
  const gainers = data.changedItems.filter((e) => e.delta >= 0.3).map((e) => e.name);
  const losers = data.changedItems.filter((e) => e.delta <= -0.3).map((e) => e.name);
  const flat = data.changedItems.filter((e) => Math.abs(e.delta) < 0.3).map((e) => e.name);
  const list = (names: string[]) => names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}` : names[0] ?? "";
  const champs = data.champions.filter((c) => c.before != null && c.after != null);

  return (
    <Container className="py-10 sm:py-14">
      <JsonLd data={breadcrumbJsonLd([{ name: "Meta", path: "/meta" }, { name: `Patch ${patch} impact`, path: `/patch-impact/${patch}` }])} />
      <JsonLd data={{
        "@context": "https://schema.org", "@type": "Article",
        headline: `What patch ${patch} did to China's Wild Rift builds`,
        datePublished: data.liveDate ?? undefined,
        author: { "@type": "Organization", name: "WrTrueMeta" },
      }} />

      <div className="max-w-3xl">
        <Link href="/meta#builds" className="text-sm font-medium text-accent hover:opacity-80">← Meta overview</Link>
        <p className="mt-4 text-xs font-semibold uppercase tracking-[0.2em] text-accent">{`Patch impact · China Legendary`}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">{`What patch ${patch} did to China's builds`}</h1>
        <p className="mt-3 text-lg leading-relaxed text-muted">
          {`Patch ${patch}${live ? ` went live on ${live}` : ""}. Comparing China's Legendary loadouts across ${data.lanes} champion-lanes, ${data.captures[data.previous]} captures on ${data.previous} against ${data.captures[patch]} on ${patch}: `}
          {gainers.length ? `${list(gainers)} gained ground` : ""}
          {gainers.length && (losers.length || flat.length) ? ", " : ""}
          {losers.length ? `${list(losers)} lost it` : ""}
          {losers.length && flat.length ? ", and " : ""}
          {flat.length ? `${list(flat)} barely moved` : ""}.
        </p>
        <p className="mt-3 text-xs leading-relaxed text-faint">
          {`Shares are of each champion-lane's games, averaged with every lane counting once: China's app gives no game counts. A shift after a patch is what players did, not proof the change caused it.`}
          {data.notesUrl && <> <a href={data.notesUrl} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">Read the official {patch} notes</a>.</>}
        </p>
      </div>

      {data.changedItems.length > 0 && (
        <section className="mt-10">
          <h2 className="text-xl font-semibold">{`Items changed in ${patch}`}</h2>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {data.changedItems.map((entry) => <EntryCard key={entry.name} entry={entry} kind="item" />)}
          </div>
        </section>
      )}

      {data.changedRunes.length > 0 && (
        <section className="mt-10">
          <h2 className="text-xl font-semibold">{`Runes changed in ${patch}`}</h2>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {data.changedRunes.map((entry) => <EntryCard key={entry.name} entry={entry} kind="rune" />)}
          </div>
        </section>
      )}

      <AdSlot placement="inline" bare className="my-10" />

      {champs.length > 0 && (
        <section className="mt-10">
          <h2 className="text-xl font-semibold">{`The champions ${patch} changed`}</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">Tencent&rsquo;s daily China win rate over every ranked game: the week before the patch against the days since.</p>
          <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {champs.map((c) => (
              <Link key={c.slug} href={`/champions/${c.slug}`} className="glass glass-hover flex items-center gap-3 rounded-xl p-3">
                <img src={c.icon} alt="" className="h-10 w-10 rounded-full" loading="lazy" />
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">{c.name}</p>
                  <p className="text-xs"><Delta before={c.before!} after={c.after!} /></p>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {(data.movedItems.length > 0 || data.movedRunes.length > 0) && (
        <section className="mt-10">
          <h2 className="text-xl font-semibold">Moved without being touched</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">{`The biggest shifts among items and runes ${patch} did not change: knock-on effects of everything else.`}</p>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {[...data.movedItems.slice(0, 4).map((e) => [e, "item"] as const), ...data.movedRunes.slice(0, 2).map((e) => [e, "rune"] as const)]
              .map(([entry, kind]) => <EntryCard key={`${kind}-${entry.name}`} entry={entry} kind={kind} />)}
          </div>
        </section>
      )}

      <p className="mt-10 text-sm text-faint">
        See this week&rsquo;s builds on the <Link href="/meta#builds" className="text-accent hover:underline">meta page</Link>, or any champion&rsquo;s loadouts across patches on its own page.
      </p>
    </Container>
  );
}
