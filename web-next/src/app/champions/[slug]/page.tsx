import type { Metadata } from "next";
import { readFileSync } from "node:fs";
import path from "node:path";
import Link from "next/link";
import { notFound } from "next/navigation";
import { site, getChampion, getChampions, pendingChampions, championsInRole, tierText, tierLabel, regionBoard } from "@/lib/data";
import { getCnBySlug, getGlobalBySlug } from "@/lib/cn";
import { getMatchups, type ResolvedMatchup } from "@/lib/counters";
import { getSkewBySlug } from "@/lib/skew";
import { getBuild, type Build } from "@/lib/builds";
import { BUILD_TOOLS_LIVE, recommendedBuildsLive } from "@/lib/flags";
import { roster, type RosterChampion } from "@/lib/threat";
import { ChampionCombo } from "@/components/champion-combo";
import { getChampionDetails, type AbilityCard } from "@/lib/champion-details";
import { getChampionHistory } from "@/lib/champion-history";
import { getPlaystyleProfile } from "@/lib/playstyle-profile";
import { TierChip, ChampionAvatar, Card } from "@/components/ui";
import { BracketCurve } from "@/components/bracket-curve";
import { ChampionTabs } from "@/components/champion-tabs";
import { ChampionHistory } from "@/components/champion-history";
import { PlaystyleProfile } from "@/components/playstyle-profile";
import { KaynAbilities, KaynFormGuide } from "@/components/kayn-forms";
import { BuildLikeButton } from "@/components/build-like";
import { ShareBuildButton } from "@/components/share-build";
import { AdSlot } from "@/components/ad-slot";
import { ToolsCta } from "@/components/tools-cta";
import { MeasuredProfile } from "@/components/measured-profile";
import { ServerBuilds } from "@/components/server-builds";
import { ChampionAnalytics, type AnalyticsPlayer } from "@/components/champion-analytics";
import { SERVER_GAP, toServerBuild } from "@/lib/server-build";
import { buildsByServer, ladderBuildsCollected } from "@/lib/ladder-build";
import { serverBuildInsights } from "@/lib/server-build-insights";
import itemsCatalogue from "@/data/items.json";
import { JsonLd, breadcrumbJsonLd } from "@/lib/structured-data";

/* eslint-disable @next/next/no-img-element */

const ARCHETYPE_LABEL: Record<string, string> = { spellcaster: "Spell-caster", autoattacker: "Auto-attacker", weaver: "Weaver", onhitcaster: "On-hit caster" };
const MECHANIC_LABEL: Record<string, string> = { cc: "Crowd control", dash: "Mobility", heal: "Healing", onHit: "On-hit", shield: "Shielding", poke: "Poke", stealth: "Stealth" };
const SCALES_LABEL: Record<string, string> = { ad: "AD", ap: "AP", maxHp: "Max HP", attackSpeed: "Attack speed", crit: "Crit", mana: "Mana", abilityHaste: "Ability haste", lethality: "Lethality" };
const pretty = (map: Record<string, string>, key: string) => map[key] ?? key;

/** Data Dragon's `loading` art is the tall champion-card crop. The matching
 *  `splash` URL is the full horizontal painting intended for wide heroes.
 *  Local overrides (such as Hecarim's 2048×934 artwork) are already wide and
 *  pass through unchanged. */
function horizontalSplash(source: string): string {
  return source.replace("/cdn/img/champion/loading/", "/cdn/img/champion/splash/");
}

function loadAnalyticsPlayers(slug: string): AnalyticsPlayer[] {
  try {
    const file = path.join(process.cwd(), "public", "players", `${slug}.json`);
    const parsed = JSON.parse(readFileSync(file, "utf8")) as { players?: AnalyticsPlayer[] };
    return (parsed.players ?? []).filter((player) =>
      Number.isFinite(player.r) && Number.isFinite(player.w) && Number.isFinite(player.g),
    );
  } catch {
    return [];
  }
}

export function generateStaticParams() {
  return [...getChampions(), ...pendingChampions()].map((champion) => ({ slug: champion.slug }));
}

export async function generateMetadata(props: PageProps<"/champions/[slug]">): Promise<Metadata> {
  const { slug } = await props.params;
  const champion = getChampion(slug);
  if (!champion) return { title: "Champion not found" };
  // Search Console shows these pages picking up "<champion> wild rift" and
  // "<champion> counter wild rift", so both the name-first title and the word
  // "counters" in the description are there to match real queries rather than
  // to describe the page to ourselves.
  const title = `${champion.name} Wild Rift Build, Counters & Win Rate`;
  // Same blended figures the page itself shows, so the snippet in search
  // results cannot quote a different tier from the one above the fold.
  const meta = getGlobalBySlug(champion.slug) ?? champion;
  const description = champion.statsPending
    ? `${champion.name} in Wild Rift: full kit, ability numbers, base stats and item build. Win rate and tier arrive once there is a ranked sample to build them from.`
    : `${champion.name} is ${tierLabel(meta.tier)} tier in Wild Rift with a ${meta.wr.toFixed(1)}% win rate across its 50 best players in EU and NA. Counters, matchups, abilities, runes, item build and full patch history.`;
  const splash = horizontalSplash(champion.splash);
  return { title, description, alternates: { canonical: `/champions/${champion.slug}` }, openGraph: { title, description, images: [splash] }, twitter: { card: "summary_large_image", title, description, images: [splash] } };
}

/** An item's name and icon for the per-server build card. Unknown slugs still
 *  render, spelled out, rather than vanishing from a build. */
const ITEM_CATALOGUE = new Map(
  (itemsCatalogue as { slug: string; name: string; icon: string }[]).map((i) => [i.slug, i]),
);
function catalogueItem(slug: string) {
  const hit = ITEM_CATALOGUE.get(slug);
  return {
    slug,
    name: hit?.name ?? slug.replace(/-/g, " "),
    icon: hit?.icon ?? `/items/${slug}.webp`,
  };
}

export default async function ChampionPage(props: PageProps<"/champions/[slug]">) {
  const { slug } = await props.params;
  const champion = getChampion(slug);
  if (!champion) notFound();
  const heroSplash = horizontalSplash(champion.splash);

  const cn = getCnBySlug(champion.slug);
  const skew = getSkewBySlug(champion.slug);
  const matchups = getMatchups(champion.slug);
  const details = getChampionDetails(champion.slug);
  const kit = roster()[champion.name] as RosterChampion | undefined;
  const built = getBuild(champion.slug);
  const archetype = (built?.builds as { archetype?: { archetype: string; reason?: string } } | undefined)?.archetype;
  const synergyNotes = built?.builds.synergyNotes ?? [];
  const standardKey = built ? built.builds.variants.find((variant) => variant === "standard" || variant === "balanced") ?? built.builds.variants[0] : null;
  const standardBuild = standardKey ? built!.builds.builds[standardKey] : null;
  const playstyle = getPlaystyleProfile(champion);
  const history = getChampionHistory(champion.name);
  const naBoard = regionBoard("NA");
  const na = naBoard.champions.find((c) => c.slug === champion.slug);
  // What each server's top 50 actually hold. Per server on purpose: see
  // components/server-builds.tsx for why China is empty and stays empty.
  const serverBuilds = buildsByServer(champion.name);
  // Headline figures come from the EU + NA blend so the top of the page
  // agrees with the tier list. Falls back to EU when a champion is missing
  // from a board, and the "Win rate by region" card below still shows each
  // server on its own, so promoting the blend hides nothing.
  const blended = getGlobalBySlug(champion.slug);
  const headline = blended ?? champion;
  const podium = champion.globalBestPlayerPodium ?? champion.bestPlayerPodium;
  const analyticsPlayers = loadAnalyticsPlayers(champion.slug);
  const related = championsInRole(champion.role).filter((entry) => entry.slug !== champion.slug).slice(0, 6);
  const stats = champion.statsPending ? [] : [
    { label: "Tier", value: tierLabel(headline.tier), className: tierText[headline.tier] },
    { label: "Win rate", value: `${headline.wr.toFixed(1)}%`, className: "text-accent" },
    { label: "Ceiling WR", value: headline.maxWr != null ? `${headline.maxWr.toFixed(1)}%` : "-", className: "text-gold" },
    { label: "Median games", value: headline.medianGames != null ? Math.round(headline.medianGames).toLocaleString() : "-", className: "" },
  ];
  const movement = headline.wrDelta ?? 0;
  const metaSignal = champion.statsPending ? "Collecting" : movement > 0.2 ? "Rising" : movement < -0.2 ? "Cooling" : "Stable";
  const signalTone = movement > 0.2 ? "text-emerald-300" : movement < -0.2 ? "text-rose-300" : "text-sky-300";

  // Put the fastest, most copyable answer directly below the hero. The
  // personalized generator follows this evidence in the same card, rather
  // than asking a visitor to scroll past several unrelated sections first.
  const serverBuildCard = (
    <Card className="rounded-[1.5rem] p-4 sm:p-5">
      <div>
        <ServerBuilds
          champion={champion.name}
          compact
          personalizeHref={`/build?champion=${champion.slug}&tab=generate`}
          builds={{
            eu: toServerBuild(serverBuilds.eu, catalogueItem,
              serverBuildInsights(champion.name, serverBuilds.eu)),
            na: toServerBuild(serverBuilds.na, catalogueItem,
              serverBuildInsights(champion.name, serverBuilds.na)),
            cn: toServerBuild(serverBuilds.cn, catalogueItem,
              serverBuildInsights(champion.name, serverBuilds.cn)),
          }}
          gaps={SERVER_GAP}
          collected={{ eu: ladderBuildsCollected("eu") ?? site.collectedOn ?? undefined, na: naBoard.collectedOn ?? undefined }}
        />
      </div>
    </Card>
  );

  // Everything in the overview is leaderboard-derived, so a champion without
  // one gets an honest placeholder instead: the kit, base stats and build tabs
  // still carry real data and stay exactly as they are.
  const pendingOverview = (
    <div className="space-y-6">
      {serverBuildCard}
      <Card className="p-5 sm:p-6">
        <h2 className="text-lg font-semibold">{champion.name} stats are pending</h2>
        <p className="mt-2 leading-relaxed text-muted">
          {champion.name} is live in Wild Rift but has no leaderboard here yet, and every
          ranking on this site is built from those players. Rather than publish a win rate we
          cannot stand behind, this page shows the kit and base stats now, and the rankings
          arrive with the first collected sample.
        </p>
        {kit?.primaryDamage && (
          <p className="mt-3 text-sm text-muted">
            <span className="font-medium text-text">Damage type:</span> {kit.primaryDamage}
            {kit.scalesWith?.length ? <> · <span className="font-medium text-text">Scales with:</span> {kit.scalesWith.join(", ")}</> : null}
          </p>
        )}
      </Card>
    </div>
  );

  const overview = (
    <div className="space-y-4">
      {serverBuildCard}
      <ChampionAnalytics
        champion={champion.name}
        players={analyticsPlayers}
        regions={[
          { label: "EU", value: Number.isFinite(champion.wr) ? champion.wr : null },
          { label: "NA", value: na && Number.isFinite(na.wr) ? na.wr : null },
          { label: "CN", value: cn && Number.isFinite(cn.wr) ? cn.wr : null },
        ]}
        winRate={headline.wr}
        winRateDelta={headline.wrDelta}
        winrateStd={headline.winrateStd}
      />
      {skew && (
        <Card className="p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-semibold">Regular-ranked performance</h2><Link href="/ranks" className={`rounded-full px-2.5 py-1 text-xs font-semibold ${skew.climbing ? "bg-emerald-400/15 text-emerald-300" : skew.stomper ? "bg-rose-400/15 text-rose-300" : "bg-white/10 text-muted"}`}>{skew.climbing ? "Improves at higher skill" : skew.stomper ? "Falls off up top" : "Stable across brackets"}</Link></div>
          <div className="mt-4 flex justify-center"><BracketCurve curve={skew.curve} skew={skew.skew} labeled width={460} height={150} className="h-auto w-full max-w-[460px]" /></div>
          {skew.legendary && <p className="mt-3 text-center text-sm text-muted">CN Legendary solo-queue benchmark: <span className="font-semibold text-gold">{skew.legendary.wr.toFixed(1)}%</span></p>}
        </Card>
      )}
      <MeasuredProfile slug={champion.slug} />
      <Card className="p-5 sm:p-6">
        <h2 className="text-lg font-semibold">Best {champion.name} player</h2>
        {champion.bestPlayer ? <p className="mt-2 leading-relaxed text-muted"><span className="font-medium text-text">{champion.bestPlayer.player}</span>{champion.bestPlayer.rank ? ` (rank #${champion.bestPlayer.rank})` : ""} leads the current regional sample with a composite Best Player score of <span className="font-medium text-accent">{champion.bestPlayer.best_score?.toFixed(1) ?? "-"}</span>, backed by a <span className="font-medium text-accent">{champion.bestPlayer.confidence_wr?.toFixed(1) ?? "-"}%</span> confidence-adjusted win rate.</p> : <p className="mt-2 text-muted">Best-player data is being collected.</p>}
      </Card>
      {podium?.players?.length ? (
        <Card className="p-5 sm:p-6">
          <div className="flex flex-wrap items-end justify-between gap-2">
            <div>
              <p className="text-[0.65rem] font-semibold uppercase tracking-[0.16em] text-gold">Top 3 this season</p>
              <h2 className="mt-1 text-lg font-semibold">The best {champion.name} players</h2>
            </div>
            <span className="text-xs text-faint">{podium.scope === "global" ? "Global · EU + NA + CN" : `${podium.server ?? "Regional"} sample`}</span>
          </div>
          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            {podium.players.slice(0, 3).map((player, index) => (
              <div key={`${player.server ?? "?"}-${player.player}-${index}`} className={`rounded-xl border p-3 ${index === 0 ? "border-gold/30 bg-gold/5" : "border-line bg-white/[0.025]"}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className={`text-lg font-semibold ${index === 0 ? "text-gold" : "text-muted"}`}>#{index + 1}</span>
                  {player.server && <span className="text-[0.65rem] font-semibold text-faint">{player.server}</span>}
                </div>
                <p className="mt-2 truncate font-medium" title={player.player}>{player.player}</p>
                <p className="mt-1 text-xs text-muted">
                  {player.winRate != null ? `${player.winRate.toFixed(1)}% WR` : "—"} · {player.games ?? "—"} games
                  {player.score != null ? ` · ${player.score.toFixed(1)} score` : ""}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs leading-relaxed text-faint">The score combines confidence-adjusted win rate, ladder strength, champion-board position, Champion Score and current-season games.</p>
        </Card>
      ) : null}
    </div>
  );

  const playstylePanel = (
    <div className="space-y-6">
      {champion.name === "Kayn" && <Card className="p-5 sm:p-6"><KaynFormGuide /></Card>}
      <Card className="p-5 sm:p-6"><PlaystyleProfile name={champion.name} profile={playstyle} /></Card>
      {(kit || archetype) && (
        <Card className="p-5 sm:p-6">
          <h2 className="text-lg font-semibold">Kit identity</h2>
          <div className="mt-4 grid gap-5 sm:grid-cols-2">
            {archetype && <div><p className="text-xs font-semibold uppercase tracking-wide text-faint">Archetype</p><p className="mt-1 font-medium text-gold">{pretty(ARCHETYPE_LABEL, archetype.archetype)}</p>{archetype.reason && <p className="mt-1 text-sm text-muted">{archetype.reason}</p>}</div>}
            {kit && <div><p className="text-xs font-semibold uppercase tracking-wide text-faint">Damage & scaling</p><p className="mt-1 text-sm"><span className="font-medium">{kit.primaryDamage === "magic" ? "Magic" : "Physical"}</span><span className="text-muted"> damage · scales with </span>{kit.scalesWith.map((scale) => pretty(SCALES_LABEL, scale)).join(", ") || "-"}</p><div className="mt-2 flex flex-wrap gap-1.5">{kit.mechanics.map((mechanic) => <span key={mechanic} className="rounded-md bg-white/[0.06] px-2 py-0.5 text-xs text-muted">{pretty(MECHANIC_LABEL, mechanic)}</span>)}</div></div>}
          </div>
          {built?.builds.attackStyle?.buildHint && <p className="mt-4 border-t border-line/60 pt-3 text-sm text-muted"><span className="font-medium text-text">Build around:</span> {built.builds.attackStyle.buildHint}.</p>}
        </Card>
      )}
      {synergyNotes.length > 0 && <Card className="p-5 sm:p-6"><h2 className="text-lg font-semibold">Kit synergies</h2><ul className="mt-4 space-y-2">{synergyNotes.map((note, index) => <li key={index} className="flex gap-2.5 text-sm text-muted"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent/70"/><span>{note}</span></li>)}</ul></Card>}
      {/* Gated on recommendedBuildsLive as well as BUILD_TOOLS_LIVE. The studio
          holds the curated catalogue back per champion while it is validated,
          and this card serves the same pre-authored build -- so without the
          second check a locked champion's build was simply readable here
          instead, which is what the gate exists to prevent. */}
      {BUILD_TOOLS_LIVE && recommendedBuildsLive(champion.name) && standardBuild && <Card className="p-5 sm:p-6"><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-semibold">Recommended build</h2><Link href={`/build?champion=${champion.slug}`} className="rounded-full bg-accent/15 px-3 py-1 text-xs font-semibold text-accent">Open Build Studio →</Link></div><BuildOrder build={standardBuild}/><div className="mt-4 flex flex-wrap items-center gap-2"><BuildLikeButton buildId={`${champion.slug}:${standardKey}`}/><ShareBuildButton path={`/build?champion=${champion.slug}&variant=${standardKey}`} title={`${champion.name} recommended build`} text={`${champion.name} recommended build on WrTrueMeta: full item order, boots timing and runes.`}/></div></Card>}
      {BUILD_TOOLS_LIVE && champion.name === "Kayn" && <Card className="p-5 sm:p-6"><h2 className="text-lg font-semibold">Form-specific build</h2><p className="mt-2 text-sm text-muted">Kayn does not have one responsible standard build: Shadow Assassin and Rhaast value different fights, runes, and items.</p><Link href="/build?champion=kayn&tab=generate" className="mt-4 inline-flex rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black">Choose a form and generate →</Link></Card>}
      {(matchups.strong.length > 0 || matchups.weak.length > 0) && <div className="grid gap-4 sm:grid-cols-2"><Matchups title={`${champion.name} is strong against`} accent="text-accent" matchups={matchups.strong}/><Matchups title={`${champion.name} is weak against`} accent="text-bad" matchups={matchups.weak}/></div>}
    </div>
  );

  const abilities = (
    <div className="space-y-6">
      <ChampionCombo name={champion.name} slug={champion.slug} />
      {details?.abilities.length ? (champion.name === "Kayn" ? <Card className="p-5 sm:p-6"><KaynAbilities shadowAbilities={details.abilities} rhaastAbilities={getChampionDetails("kayn-rhaast")?.abilities} /></Card> : <Card className="p-5 sm:p-6"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold">{champion.name} abilities</h2>{details.skillPriority.length > 0 && <div className="flex items-center gap-1 text-xs text-muted"><span>Max:</span>{details.skillPriority.map((key, index) => <span key={key} className="flex items-center gap-1"><b className="grid h-6 w-6 place-items-center rounded-md bg-accent/20 text-accent">{key}</b>{index < details.skillPriority.length - 1 && <span>›</span>}</span>)}</div>}</div><div className="mt-5 space-y-4">{details.abilities.map((ability) => <Ability key={`${ability.slot}-${ability.name}`} ability={ability}/>)}</div></Card>) : null}
      {details && Object.keys(details.baseStats).length > 0 && <Card className="p-5 sm:p-6"><h2 className="text-lg font-semibold">Base stats</h2><p className="mt-1 text-sm text-muted">Level 1 and level 15 values before items and runes.</p><BaseStats stats={details.baseStats}/></Card>}
    </div>
  );

  return (
    <>
      <JsonLd
        data={breadcrumbJsonLd([
          { name: "Champions", path: "/champions" },
          { name: champion.name, path: `/champions/${champion.slug}` },
        ])}
      />
      <div
        className="no-plate min-h-screen overflow-x-clip"
        style={{ backgroundImage: "radial-gradient(circle at 18% 8%, rgba(72,137,235,.22), transparent 29rem), radial-gradient(circle at 88% 34%, rgba(53,175,188,.1), transparent 24rem), linear-gradient(180deg,rgba(10,22,38,.86) 0%,rgba(8,19,33,.9) 50%,rgba(7,17,31,.94) 100%)" }}
      >
        <section className="relative overflow-hidden pt-7 sm:pt-9">
          <div className="mx-auto max-w-[1280px] px-4 sm:px-6">
            <Link href="/champions" className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted transition hover:text-text">← Champion atlas</Link>
            <div className="glass relative mt-4 grid overflow-hidden rounded-[1.75rem] border border-white/[0.11] shadow-[0_28px_100px_rgba(0,0,0,.34)] lg:grid-cols-[.88fr_1.12fr]">
              <div className="relative z-10 order-2 flex flex-col justify-between p-6 lg:order-1 lg:min-h-[248px] lg:px-7 lg:py-6">
                <div>
                  <div className="flex items-center gap-4">
                    <ChampionAvatar champion={champion} size={72} showBadges={false}/>
                    <div className="min-w-0">
                      <p className="text-[0.62rem] font-semibold uppercase tracking-[0.2em] text-accent">Champion profile</p>
                      <div className="mt-1 flex items-center gap-2">
                        <h1 className="truncate text-4xl leading-[0.98] tracking-[-0.045em] sm:text-[3.2rem]" style={{ fontFamily: "var(--font-sans)", fontWeight: 800 }}>{champion.name}</h1>
                        {champion.isOtp && <span className="rounded-md bg-orange-500/90 px-1.5 py-0.5 text-[10px] font-bold text-white">OTP</span>}
                      </div>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs font-medium text-muted">
                    <span className="rounded-full border border-white/[0.09] bg-white/[0.045] px-3 py-1.5">{champion.role}</span>
                    <span className="rounded-full border border-white/[0.09] bg-white/[0.045] px-3 py-1.5">{champion.class}</span>
                    <span className={`rounded-full border border-white/[0.09] bg-white/[0.045] px-3 py-1.5 ${champion.isHard ? "text-rose-300" : ""}`}>{champion.difficultyLabel}</span>
                  </div>
                </div>
                {stats.length ? (
                  <div className="mt-5 grid grid-cols-2 overflow-hidden rounded-2xl border border-white/[0.08] bg-black/15 sm:grid-cols-4 lg:grid-cols-4">
                    {stats.map((stat, index) => (
                      <div key={stat.label} className={`p-3.5 sm:p-4 ${index % 2 ? "border-l border-white/[0.07]" : ""} ${index > 1 ? "border-t border-white/[0.07] sm:border-t-0 lg:border-t xl:border-t-0" : ""}`}>
                        <p className="text-[0.58rem] font-semibold uppercase tracking-[0.14em] text-faint">{stat.label}</p>
                        <p className={`mt-1.5 text-lg font-semibold ${stat.className}`}>{stat.value}</p>
                      </div>
                    ))}
                  </div>
                ) : <p className="mt-8 text-sm text-muted">Leaderboard sample pending.</p>}
              </div>

              <div className="relative order-1 min-h-[260px] overflow-hidden lg:order-2 lg:min-h-[248px]">
                <img src={heroSplash} alt="" className="absolute inset-0 h-full w-full object-cover object-center" />
                <div className="absolute inset-0 bg-gradient-to-t from-[#07101d] via-transparent to-black/10 lg:bg-gradient-to-r lg:from-[#08101d] lg:via-transparent lg:to-transparent" />
                <div className="absolute inset-0 bg-gradient-to-t from-[#07101d]/80 via-transparent to-transparent lg:hidden" />
                <div className="absolute bottom-4 left-4 right-4 rounded-2xl border border-white/[0.13] bg-[#07101d]/75 p-4 shadow-2xl backdrop-blur-xl sm:bottom-5 sm:left-auto sm:right-5 sm:w-[16.5rem]">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-[0.58rem] font-semibold uppercase tracking-[0.18em] text-faint">Meta signal</p>
                      <p className={`mt-1 text-lg font-semibold ${signalTone}`}>{metaSignal}</p>
                    </div>
                    <svg viewBox="0 0 98 38" className="w-24" role="img" aria-label={`${metaSignal} collection trend`}>
                      <path d={movement < -0.2 ? "M3 8 C20 10 29 14 44 13 S69 25 95 30" : movement > 0.2 ? "M3 30 C20 29 28 23 43 24 S70 12 95 7" : "M3 21 C20 18 31 22 45 19 S70 20 95 17"} fill="none" stroke={movement < -0.2 ? "#fb7185" : movement > 0.2 ? "#6ee7c7" : "#7cb8ff"} strokeWidth="3" strokeLinecap="round" />
                    </svg>
                  </div>
                  <div className="mt-3 flex items-center justify-between border-t border-white/[0.08] pt-3 text-[0.68rem] text-muted">
                    <span>{analyticsPlayers.length || 50} tracked players</span>
                    <span className={signalTone}>{headline.wrDelta == null ? "Fresh sample" : `${movement >= 0 ? "+" : ""}${movement.toFixed(1)} pp`}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <div className="mx-auto max-w-[1280px] px-4 pb-10 pt-4 sm:px-6 sm:pb-12 sm:pt-4">
          <ChampionTabs
            panels={{ overview: champion.statsPending ? pendingOverview : overview, playstyle: playstylePanel, abilities, history: <ChampionHistory name={champion.name} changes={history.changes} summary={history.summary}/> }}
          />
          <ToolsCta />
          {/* In-content, after the champion's own material and before the
              "other champions" grid: the seam where a reader has finished what
              they came for. */}
          <AdSlot placement="inline" bare className="my-8" />
          {related.length > 0 && <div className="mt-10"><h2 className="mb-4 text-lg font-semibold">Other {champion.role} champions</h2><div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">{related.map((entry) => <Link key={entry.slug} href={`/champions/${entry.slug}`} className="glass glass-hover flex flex-col items-center gap-2 rounded-xl p-3 text-center"><ChampionAvatar champion={entry} size={48}/><span className="w-full truncate text-sm font-medium">{entry.name}</span><div className="flex items-center gap-1.5"><TierChip tier={entry.tier}/><span className="text-xs font-semibold text-accent">{entry.wr.toFixed(1)}%</span></div></Link>)}</div></div>}
        </div>
      </div>
    </>
  );
}

function Ability({ ability }: { ability: AbilityCard }) {
  return <div className="flex gap-3.5"><div className="relative shrink-0">{ability.icon ? <img src={ability.icon} alt={ability.name} width={48} height={48} className="rounded-lg ring-1 ring-white/10"/> : <span className="grid h-12 w-12 place-items-center rounded-lg bg-white/[0.06] text-sm font-bold text-faint">{ability.key}</span>}<span className="absolute -left-1.5 -top-1.5 grid h-5 min-w-5 place-items-center rounded-full bg-[#0e1322] px-1 text-[0.6rem] font-bold text-accent ring-1 ring-line">{ability.key}</span></div><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="font-semibold">{ability.name}</span>{ability.cooldowns.length > 0 && <span className="text-[0.7rem] text-faint">CD {ability.cooldowns.join(" / ")}s</span>}</div>{ability.text && <p className="mt-1 text-sm leading-relaxed text-muted">{ability.text}</p>}</div></div>;
}

const BASE_STAT_ROWS: [string, string][] = [["hp", "Health"], ["ad", "Attack Damage"], ["armor", "Armor"], ["mr", "Magic Resist"], ["attackSpeed", "Attack Speed"], ["moveSpeed", "Move Speed"], ["mana", "Mana"], ["hpRegen", "HP Regen (5s)"], ["manaRegen", "Mana Regen (5s)"]];

function BaseStats({ stats }: { stats: Record<string, { base: number; perLevel: number; lvl15?: number }> }) {
  const format = (value: number) => Number.isInteger(value) ? value.toString() : value.toFixed(value < 3 ? 3 : 1);
  return <div className="mt-4 overflow-x-auto"><table className="w-full min-w-[320px] text-sm"><thead><tr className="text-left text-xs uppercase tracking-wide text-faint"><th className="pb-2">Stat</th><th className="pb-2 text-right">Level 1</th><th className="pb-2 text-right">Level 15</th></tr></thead><tbody>{BASE_STAT_ROWS.filter(([key]) => stats[key]).map(([key, label]) => { const stat = stats[key]; const level15 = stat.lvl15 ?? stat.base + stat.perLevel * 14; return <tr key={key} className="border-t border-line/60"><td className="py-2 text-muted">{label}</td><td className="py-2 text-right font-medium">{format(stat.base)}</td><td className="py-2 text-right font-medium text-accent">{format(level15)}</td></tr>; })}</tbody></table></div>;
}

function BuildOrder({ build }: { build: Build }) {
  return <div className="mt-4 flex flex-wrap items-center gap-2">{build.coreBuild.map((item, index) => <span key={item.slug} className="relative" title={item.reason ? `${item.name} · ${item.reason}` : item.name}><img src={item.icon} alt={item.name} width={44} height={44} className={`rounded-lg ${item.core ? "ring-2 ring-gold" : "ring-1 ring-white/10"}`}/><span className="absolute -left-1.5 -top-1.5 grid h-[18px] w-[18px] place-items-center rounded-full bg-[#0e1322] text-[0.6rem] font-bold text-accent ring-1 ring-line">{index + 1}</span></span>)}{build.boots && <img src={build.boots.icon} alt={build.boots.name} title={build.boots.name} width={40} height={40} className="rounded-lg ring-1 ring-gold/40"/>}</div>;
}

function Matchups({ title, accent, matchups }: { title: string; accent: string; matchups: ResolvedMatchup[] }) {
  return <Card className="p-5"><h2 className={`text-sm font-semibold ${accent}`}>{title}</h2><div className="mt-4 space-y-2">{matchups.slice(0, 5).map(({ champion, reason }) => <div key={champion.slug} className="relative rounded-lg border border-transparent transition hover:border-line/60 hover:bg-white/[0.035]"><Link href={`/champions/${champion.slug}`} className="group flex items-center gap-3 py-2 pl-2 pr-11"><ChampionAvatar champion={champion} size={42} showBadges={false}/><span className="min-w-0 truncate text-sm font-medium group-hover:text-accent">{champion.name}</span></Link>{reason && <><button type="button" aria-label={`Why ${champion.name} is in this list`} className="peer absolute right-2 top-2.5 grid h-7 w-7 place-items-center rounded-full border border-line bg-bg/80 text-xs font-bold text-muted transition hover:border-accent/50 hover:text-accent focus:border-accent/50 focus:text-accent focus:outline-none">i</button><span role="tooltip" className="pointer-events-none invisible absolute right-2 top-10 z-20 w-[min(260px,calc(100vw-4rem))] rounded-lg border border-line bg-[#111827] p-3 text-xs leading-relaxed text-muted opacity-0 shadow-2xl transition peer-hover:visible peer-hover:opacity-100 peer-focus:visible peer-focus:opacity-100">{reason}</span></>}</div>)}</div></Card>;
}
