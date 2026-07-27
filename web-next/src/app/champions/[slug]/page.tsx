import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getChampion, getChampions, pendingChampions, championsInRole, tierText, tierLabel } from "@/lib/data";
import { getCnBySlug } from "@/lib/cn";
import { getMatchups, type ResolvedMatchup } from "@/lib/counters";
import { getSkewBySlug } from "@/lib/skew";
import { getBuild, type Build } from "@/lib/builds";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";
import { roster, type RosterChampion } from "@/lib/threat";
import { getChampionDetails, type AbilityCard } from "@/lib/champion-details";
import { getChampionHistory } from "@/lib/champion-history";
import { getPlaystyleProfile } from "@/lib/playstyle-profile";
import { Container, TierChip, ChampionAvatar, Card } from "@/components/ui";
import { BracketCurve } from "@/components/bracket-curve";
import { ChampionTabs } from "@/components/champion-tabs";
import { ChampionHistory } from "@/components/champion-history";
import { PlaystyleProfile } from "@/components/playstyle-profile";
import { KaynAbilities, KaynFormGuide } from "@/components/kayn-forms";
import { BuildLikeButton } from "@/components/build-like";
import { ShareBuildButton } from "@/components/share-build";
import { ToolsCta } from "@/components/tools-cta";
import { JsonLd, breadcrumbJsonLd } from "@/lib/structured-data";

/* eslint-disable @next/next/no-img-element */

const ARCHETYPE_LABEL: Record<string, string> = { spellcaster: "Spell-caster", autoattacker: "Auto-attacker", weaver: "Weaver", onhitcaster: "On-hit caster" };
const MECHANIC_LABEL: Record<string, string> = { cc: "Crowd control", dash: "Mobility", heal: "Healing", onHit: "On-hit", shield: "Shielding", poke: "Poke", stealth: "Stealth" };
const SCALES_LABEL: Record<string, string> = { ad: "AD", ap: "AP", maxHp: "Max HP", attackSpeed: "Attack speed", crit: "Crit", mana: "Mana", abilityHaste: "Ability haste", lethality: "Lethality" };
const pretty = (map: Record<string, string>, key: string) => map[key] ?? key;

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
  const description = champion.statsPending
    ? `${champion.name} in Wild Rift: full kit, ability numbers, base stats and item build. Win rate and tier arrive once there is a ranked sample to build them from.`
    : `${champion.name} is ${tierLabel(champion.tier)} tier in Wild Rift with a ${champion.wr.toFixed(1)}% win rate across its 50 best EU players. Counters, matchups, abilities, runes, item build and full patch history.`;
  return { title, description, alternates: { canonical: `/champions/${champion.slug}` }, openGraph: { title, description, images: [champion.splash] }, twitter: { card: "summary_large_image", title, description, images: [champion.splash] } };
}

export default async function ChampionPage(props: PageProps<"/champions/[slug]">) {
  const { slug } = await props.params;
  const champion = getChampion(slug);
  if (!champion) notFound();

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
  const related = championsInRole(champion.role).filter((entry) => entry.slug !== champion.slug).slice(0, 6);
  const stats = champion.statsPending ? [] : [
    { label: "Tier", value: tierLabel(champion.tier), className: tierText[champion.tier] },
    { label: "Win rate", value: `${champion.wr.toFixed(1)}%`, className: "text-accent" },
    { label: "Ceiling WR", value: champion.maxWr != null ? `${champion.maxWr.toFixed(1)}%` : "-", className: "text-gold" },
    { label: "Median games", value: champion.medianGames != null ? champion.medianGames.toLocaleString() : "-", className: "" },
  ];

  // Everything in the overview is leaderboard-derived, so a champion without
  // one gets an honest placeholder instead: the kit, base stats and build tabs
  // still carry real data and stay exactly as they are.
  const pendingOverview = (
    <div className="space-y-6">
      <Card className="p-5 sm:p-6">
        <h2 className="text-lg font-semibold">{champion.name} stats are pending</h2>
        <p className="mt-2 leading-relaxed text-muted">
          {champion.name} is live in Wild Rift but has no top-50 leaderboard here yet, and every
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
    <div className="space-y-6">
      <Card className="p-5 sm:p-6">
        <h2 className="text-lg font-semibold">{champion.name} at a glance</h2>
        <p className="mt-2 leading-relaxed text-muted">
          {champion.name} is currently <span className="font-medium text-text">{tierLabel(champion.tier)} tier</span> in EU Wild Rift, with a top-50-main win rate of <span className="font-medium text-accent">{champion.wr.toFixed(1)}%</span>. The best tracked main peaks at <span className="font-medium text-gold">{champion.maxWr != null ? `${champion.maxWr.toFixed(1)}%` : "-"}</span>.
        </p>
      </Card>
      <Card className="p-5 sm:p-6">
        <h2 className="text-lg font-semibold">Win rate by region</h2>
        <p className="mt-1 text-sm text-muted">A consistent 50%-centred scale makes regional performance easier to compare.</p>
        <div className="mt-4 grid grid-cols-3 gap-2 sm:gap-3">
          <RegionStat label="EU" wr={champion.wr} sub={`${champion.tier} tier`} />
          {cn ? <RegionStat label="CN" wr={cn.wr} sub={`${cn.cnPickRate.toFixed(1)}% pick`} /> : <RegionStat label="CN" />}
          <RegionStat label="NA" />
        </div>
      </Card>
      {skew && (
        <Card className="p-5 sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-semibold">Regular-ranked performance</h2><Link href="/ranks" className={`rounded-full px-2.5 py-1 text-xs font-semibold ${skew.climbing ? "bg-emerald-400/15 text-emerald-300" : skew.stomper ? "bg-rose-400/15 text-rose-300" : "bg-white/10 text-muted"}`}>{skew.climbing ? "Improves at higher skill" : skew.stomper ? "Falls off up top" : "Stable across brackets"}</Link></div>
          <div className="mt-4 flex justify-center"><BracketCurve curve={skew.curve} skew={skew.skew} labeled width={460} height={150} className="h-auto w-full max-w-[460px]" /></div>
          {skew.legendary && <p className="mt-3 text-center text-sm text-muted">CN Legendary solo-queue benchmark: <span className="font-semibold text-gold">{skew.legendary.wr.toFixed(1)}%</span></p>}
        </Card>
      )}
      <Card className="p-5 sm:p-6">
        <h2 className="text-lg font-semibold">Best {champion.name} player</h2>
        {champion.bestPlayer ? <p className="mt-2 leading-relaxed text-muted"><span className="font-medium text-text">{champion.bestPlayer.player}</span>{champion.bestPlayer.rank ? ` (rank #${champion.bestPlayer.rank})` : ""} leads the EU sample with a confidence-adjusted win rate of <span className="font-medium text-accent">{champion.bestPlayer.confidence_wr?.toFixed(1) ?? "-"}%</span>.</p> : <p className="mt-2 text-muted">Best-player data is being collected.</p>}
      </Card>
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
      {BUILD_TOOLS_LIVE && standardBuild && <Card className="p-5 sm:p-6"><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-lg font-semibold">Recommended build</h2><Link href={`/build?champion=${champion.slug}`} className="rounded-full bg-accent/15 px-3 py-1 text-xs font-semibold text-accent">Open Build Studio →</Link></div><BuildOrder build={standardBuild}/><div className="mt-4 flex flex-wrap items-center gap-2"><BuildLikeButton buildId={`${champion.slug}:${standardKey}`}/><ShareBuildButton path={`/build?champion=${champion.slug}&variant=${standardKey}`} title={`${champion.name} recommended build`} text={`${champion.name} recommended build on WrTrueMeta: full item order, boots timing and runes.`}/></div></Card>}
      {BUILD_TOOLS_LIVE && champion.name === "Kayn" && <Card className="p-5 sm:p-6"><h2 className="text-lg font-semibold">Form-specific build</h2><p className="mt-2 text-sm text-muted">Kayn does not have one responsible standard build: Shadow Assassin and Rhaast value different fights, runes, and items.</p><Link href="/build?champion=kayn&tab=generate" className="mt-4 inline-flex rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black">Choose a form and generate →</Link></Card>}
      {(matchups.strong.length > 0 || matchups.weak.length > 0) && <div className="grid gap-4 sm:grid-cols-2"><Matchups title={`${champion.name} is strong against`} accent="text-accent" matchups={matchups.strong}/><Matchups title={`${champion.name} is weak against`} accent="text-bad" matchups={matchups.weak}/></div>}
    </div>
  );

  const abilities = (
    <div className="space-y-6">
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
      <section className="relative overflow-hidden border-b border-line">
        <div className="absolute inset-0 bg-cover opacity-40" style={{ backgroundImage: `url(${champion.splash})`, backgroundPosition: "center 22%" }}/><div className="absolute inset-0 bg-gradient-to-r from-bg via-bg/85 to-bg/30"/><div className="absolute inset-0 bg-gradient-to-t from-bg to-transparent"/>
        <Container className="relative py-10 sm:py-14"><Link href="/champions" className="text-sm text-muted hover:text-text">← All champions</Link><div className="mt-5 flex items-center gap-4"><ChampionAvatar champion={champion} size={72} showBadges={false}/><div className="min-w-0"><div className="flex items-center gap-2"><h1 className="truncate text-3xl font-semibold tracking-tight sm:text-4xl">{champion.name}</h1>{champion.isOtp && <span className="rounded bg-orange-500 px-1.5 py-0.5 text-[10px] font-bold text-white">OTP</span>}</div><p className="mt-1 text-muted">{champion.role} · {champion.class} · <span className={champion.isHard ? "text-bad" : ""}>{champion.difficultyLabel}</span></p></div></div></Container>
      </section>
      {/* Tool cards go BELOW the hero here, not above it (the global ToolsCta
          skips champion detail pages for exactly this reason). */}
      <ToolsCta />
      <Container className="py-8 sm:py-10">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{stats.map((stat) => <Card key={stat.label} className="p-4"><p className="text-[0.65rem] font-semibold uppercase tracking-wide text-muted">{stat.label}</p><p className={`mt-2 text-xl font-semibold sm:text-2xl ${stat.className}`}>{stat.value}</p></Card>)}</div>
        <ChampionTabs panels={{ overview: champion.statsPending ? pendingOverview : overview, playstyle: playstylePanel, abilities, history: <ChampionHistory name={champion.name} changes={history.changes} summary={history.summary}/> }}/>
        {related.length > 0 && <div className="mt-10"><h2 className="mb-4 text-lg font-semibold">Other {champion.role} champions</h2><div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">{related.map((entry) => <Link key={entry.slug} href={`/champions/${entry.slug}`} className="glass glass-hover flex flex-col items-center gap-2 rounded-xl p-3 text-center"><ChampionAvatar champion={entry} size={48}/><span className="w-full truncate text-sm font-medium">{entry.name}</span><div className="flex items-center gap-1.5"><TierChip tier={entry.tier}/><span className="text-xs font-semibold text-accent">{entry.wr.toFixed(1)}%</span></div></Link>)}</div></div>}
      </Container>
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

function RegionStat({ label, wr, sub }: { label: string; wr?: number; sub?: string }) {
  return <div className="glass min-w-0 rounded-xl p-3 text-center sm:p-4"><div className="text-xs font-bold uppercase tracking-wide text-faint">{label}</div>{wr == null ? <div className="mt-2 text-sm text-faint">soon</div> : <><div className={`mt-1.5 text-xl font-semibold sm:text-2xl ${wr >= 50 ? "text-accent" : "text-muted"}`}>{wr.toFixed(1)}%</div>{sub && <div className="mt-0.5 truncate text-[0.65rem] text-muted">{sub}</div>}</>}</div>;
}
