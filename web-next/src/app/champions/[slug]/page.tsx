import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getChampion, getChampions, championsInRole, tierText, tierLabel, type Champion } from "@/lib/data";
import { getCnBySlug } from "@/lib/cn";
import { getMatchups } from "@/lib/counters";
import { getSkewBySlug } from "@/lib/skew";
import { getBuild, type Build } from "@/lib/builds";
import { BUILD_TOOLS_LIVE } from "@/lib/flags";
import { roster, type RosterChampion } from "@/lib/threat";
import { getChampionDetails, type AbilityCard } from "@/lib/champion-details";
import { Container, TierChip, ChampionAvatar, Card } from "@/components/ui";
import { BracketCurve } from "@/components/bracket-curve";

/* eslint-disable @next/next/no-img-element */

const ARCHETYPE_LABEL: Record<string, string> = {
  spellcaster: "Spell-caster", autoattacker: "Auto-attacker",
  weaver: "Weaver", onhitcaster: "On-hit caster",
};
const MECHANIC_LABEL: Record<string, string> = {
  cc: "Crowd control", dash: "Mobility", heal: "Healing",
  onHit: "On-hit", shield: "Shielding", poke: "Poke", stealth: "Stealth",
};
const SCALES_LABEL: Record<string, string> = {
  ad: "AD", ap: "AP", maxHp: "Max HP", attackSpeed: "Attack speed",
  crit: "Crit", mana: "Mana", abilityHaste: "Ability haste", lethality: "Lethality",
};
const pretty = (map: Record<string, string>, k: string) => map[k] ?? k;

export function generateStaticParams() {
  return getChampions().map((c) => ({ slug: c.slug }));
}

export async function generateMetadata(
  props: PageProps<"/champions/[slug]">
): Promise<Metadata> {
  const { slug } = await props.params;
  const c = getChampion(slug);
  if (!c) return { title: "Champion not found" };
  const title = `${c.name} Wild Rift Win Rate, Tier & Stats`;
  const desc = `${c.name} is ${tierLabel(c.tier)} tier in Wild Rift with a ${c.wr.toFixed(1)}% top-50 EU win rate. See ${c.name}'s stats, best player and role.`;
  return {
    title,
    description: desc,
    alternates: { canonical: `/champions/${c.slug}` },
    openGraph: { title, description: desc, images: [c.splash] },
    twitter: { card: "summary_large_image", title, description: desc, images: [c.splash] },
  };
}

export default async function ChampionPage(props: PageProps<"/champions/[slug]">) {
  const { slug } = await props.params;
  const c = getChampion(slug);
  if (!c) notFound();

  const cn = getCnBySlug(c.slug);
  const skew = getSkewBySlug(c.slug);
  const { strong, weak } = getMatchups(c.slug);

  // kit + build enrichment (may be missing for champions without generated data)
  const details = getChampionDetails(c.slug);
  const kit = roster()[c.name] as RosterChampion | undefined;
  const built = getBuild(c.slug);
  const arch = (built?.builds as { archetype?: { archetype: string; reason?: string } } | undefined)?.archetype;
  const synergyNotes = built?.builds.synergyNotes ?? [];
  const stdKey = built
    ? built.builds.variants.find((v) => v === "standard" || v === "balanced") ?? built.builds.variants[0]
    : null;
  const stdBuild = stdKey ? built!.builds.builds[stdKey] : null;

  const related = championsInRole(c.role)
    .filter((x) => x.slug !== c.slug)
    .slice(0, 6);

  const stats = [
    { label: "Tier", value: tierLabel(c.tier), cls: tierText[c.tier] },
    { label: "Win rate", value: `${c.wr.toFixed(1)}%`, cls: "text-accent" },
    { label: "Ceiling WR", value: c.maxWr != null ? `${c.maxWr.toFixed(1)}%` : "-", cls: "text-gold" },
    { label: "Median games", value: c.medianGames != null ? c.medianGames.toLocaleString() : "-", cls: "" },
  ];

  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-line">
        <div
          className="absolute inset-0 bg-cover opacity-40"
          style={{ backgroundImage: `url(${c.splash})`, backgroundPosition: "center 22%" }}
        />
        <div className="absolute inset-0 bg-gradient-to-r from-bg via-bg/85 to-bg/30" />
        <div className="absolute inset-0 bg-gradient-to-t from-bg to-transparent" />
        <Container className="relative py-14">
          <Link href="/champions" className="text-sm text-muted transition hover:text-text">
            ← All champions
          </Link>
          <div className="mt-5 flex items-center gap-4">
            <ChampionAvatar champion={c} size={72} showBadges={false} />
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{c.name}</h1>
                {c.isOtp && (
                  <span className="rounded bg-gradient-to-br from-orange-400 to-orange-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
                    OTP
                  </span>
                )}
              </div>
              <p className="mt-1 text-muted">
                {c.role} · {c.class} ·{" "}
                <span className={c.isHard ? "text-bad" : ""}>{c.difficultyLabel}</span>
              </p>
            </div>
          </div>
        </Container>
      </section>

      <Container className="py-10">
        {/* Stats */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stats.map((s) => (
            <Card key={s.label} className="p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">{s.label}</p>
              <p className={`mt-2 text-2xl font-semibold ${s.cls}`}>{s.value}</p>
            </Card>
          ))}
        </div>

        {/* Win rate context */}
        <Card className="mt-6 p-6">
          <h2 className="text-lg font-semibold">{c.name} win rate &amp; tier</h2>
          <p className="mt-2 text-muted">
            {c.name} is currently <span className="font-medium text-text">{tierLabel(c.tier)} tier</span> in
            EU Wild Rift. Its win rate is shown{" "}
            <span className="font-medium text-text">relative to the average champion</span> (50% =
            average), currently{" "}
            <span className="font-medium text-accent">{c.wr.toFixed(1)}%</span>. These are each
            champion&rsquo;s top-50 mains, so we centre the scale to make the gap between champions
            readable. The best {c.name} main still peaks at{" "}
            <span className="font-medium text-gold">
              {c.maxWr != null ? `${c.maxWr.toFixed(1)}%` : "-"}
            </span>{" "}
            (a real win rate).
          </p>
        </Card>

        {/* Abilities + skill order */}
        {details && details.abilities.length > 0 && (
          <Card className="mt-6 p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-lg font-semibold">{c.name} abilities</h2>
              {details.skillPriority.length > 0 && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-xs font-semibold uppercase tracking-wide text-faint">Max order</span>
                  <div className="flex items-center gap-1">
                    {details.skillPriority.map((k, i) => (
                      <span key={k} className="flex items-center gap-1">
                        <span className="grid h-6 w-6 place-items-center rounded-md bg-accent/20 text-xs font-bold text-accent">{k}</span>
                        {i < details.skillPriority.length - 1 && <span className="text-faint">›</span>}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="mt-4 space-y-3">
              {details.abilities.map((a) => <Ability key={a.slot + a.name} a={a} />)}
            </div>
          </Card>
        )}

        {/* Base stats */}
        {details && Object.keys(details.baseStats).length > 0 && (
          <Card className="mt-6 p-6">
            <h2 className="text-lg font-semibold">{c.name} base stats</h2>
            <p className="mt-1 text-sm text-muted">Level 1 base and level 15 values.</p>
            <BaseStats stats={details.baseStats} />
          </Card>
        )}

        {/* Kit & playstyle */}
        {(kit || arch) && (
          <Card className="mt-6 p-6">
            <h2 className="text-lg font-semibold">{c.name} kit &amp; playstyle</h2>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              {arch && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-faint">Archetype</p>
                  <p className="mt-1">
                    <span className="font-medium text-gold">{pretty(ARCHETYPE_LABEL, arch.archetype)}</span>
                    {arch.reason && <span className="mt-0.5 block text-sm text-muted">{arch.reason}</span>}
                  </p>
                </div>
              )}
              {kit && (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-faint">Damage &amp; scaling</p>
                  <p className="mt-1 text-sm">
                    <span className="font-medium text-text">{kit.primaryDamage === "magic" ? "Magic" : "Physical"}</span>
                    <span className="text-muted"> damage · scales with </span>
                    <span className="font-medium text-text">
                      {kit.scalesWith.map((s) => pretty(SCALES_LABEL, s)).join(", ") || "-"}
                    </span>
                  </p>
                  {kit.mechanics.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {kit.mechanics.map((m) => (
                        <span key={m} className="rounded-md bg-white/[0.06] px-2 py-0.5 text-xs text-muted">
                          {pretty(MECHANIC_LABEL, m)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
            {built?.builds.attackStyle?.buildHint && (
              <p className="mt-4 border-t border-line/60 pt-3 text-sm text-muted">
                <span className="font-medium text-text">Build around:</span> {built.builds.attackStyle.buildHint}.
              </p>
            )}
          </Card>
        )}

        {/* Synergies */}
        {synergyNotes.length > 0 && (
          <Card className="mt-6 p-6">
            <h2 className="text-lg font-semibold">{c.name} synergies</h2>
            <p className="mt-1 text-sm text-muted">How {c.name}&rsquo;s kit interacts with items, runes and stats.</p>
            <ul className="mt-4 space-y-2">
              {synergyNotes.map((s, i) => (
                <li key={i} className="flex gap-2.5 text-sm text-muted">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent/70" />
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}

        {/* Recommended build & upgrade order. Hidden until the Build Optimizer
            launches, since the build data comes from it. */}
        {BUILD_TOOLS_LIVE && stdBuild && (
          <Card className="mt-6 p-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold">{c.name} recommended build</h2>
              <Link href="/build" className="rounded-full bg-accent/15 px-3 py-1 text-xs font-semibold text-accent transition hover:bg-accent/25">
                Open the optimizer →
              </Link>
            </div>
            <p className="mt-1 text-sm text-muted">Core items in purchase order. Open the optimizer for playstyles, runes and enemy-aware swaps.</p>
            <BuildOrder build={stdBuild} />
          </Card>
        )}

        {/* Strong / weak against */}
        {(strong.length > 0 || weak.length > 0) && (
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <Matchups title={`${c.name} is strong against`} accent="text-accent" champions={strong} />
            <Matchups title={`${c.name} is weak against`} accent="text-bad" champions={weak} />
          </div>
        )}

        {/* Win rate by region */}
        <Card className="mt-6 p-6">
          <h2 className="text-lg font-semibold">Win rate by region</h2>
          <p className="mt-1 text-sm text-muted">
            Same 50%-centred scale across servers, so you can compare regions directly.
          </p>
          <div className="mt-4 grid grid-cols-3 gap-3">
            <RegionStat label="EU" wr={c.wr} sub={`${c.tier} tier · top 50`} />
            {cn ? (
              <RegionStat
                label="CN"
                wr={cn.wr}
                sub={`${cn.role} · ${cn.cnPickRate.toFixed(1)}% pick · Challenger+`}
              />
            ) : (
              <RegionStat label="CN" />
            )}
            <RegionStat label="NA" />
          </div>
        </Card>

        {/* Win rate by rank (CN skill brackets) */}
        {skew && (
          <Card className="mt-6 p-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold">{c.name} win rate by rank</h2>
              <Link
                href="/ranks"
                className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                  skew.climbing
                    ? "bg-emerald-400/15 text-emerald-300"
                    : skew.stomper
                      ? "bg-rose-400/15 text-rose-300"
                      : "bg-white/10 text-muted"
                }`}
              >
                {skew.climbing ? "Scales with elo" : skew.stomper ? "Falls off up top" : "Stable across ranks"}
              </Link>
            </div>
            <p className="mt-1 text-sm text-muted">
              How {c.name} performs from the whole ladder up to China&rsquo;s Challenger+ bracket.
            </p>
            <div className="mt-4 flex justify-center">
              <BracketCurve curve={skew.curve} skew={skew.skew} labeled width={460} height={150} className="h-auto w-full max-w-[460px]" />
            </div>
            <p className="mt-3 text-sm text-muted">
              {skew.climbing ? (
                <>
                  {c.name} <span className="font-medium text-emerald-300">gains {skew.skew.toFixed(1)} win rate</span>{" "}
                  from all ranks to Challenger+, a high-skill pick that rewards mastery.
                </>
              ) : skew.stomper ? (
                <>
                  {c.name} <span className="font-medium text-rose-300">loses {Math.abs(skew.skew).toFixed(1)} win rate</span>{" "}
                  against Challenger+ play, great for climbing, less so at the very top.
                </>
              ) : (
                <>{c.name} holds a steady win rate across every rank, a reliable, elo-agnostic pick.</>
              )}
            </p>
          </Card>
        )}

        {/* Best player */}
        <Card className="mt-6 p-6">
          <h2 className="text-lg font-semibold">Best {c.name} player</h2>
          {c.bestPlayer ? (
            <p className="mt-2 text-muted">
              The best {c.name} player tracked on EU is{" "}
              <span className="font-medium text-text">{c.bestPlayer.player}</span>
              {c.bestPlayer.rank ? ` (rank #${c.bestPlayer.rank})` : ""}, with a
              confidence-adjusted win rate of{" "}
              <span className="font-medium text-accent">
                {c.bestPlayer.confidence_wr != null
                  ? `${c.bestPlayer.confidence_wr.toFixed(1)}%`
                  : "-"}
              </span>
              . This uses the Wilson lower bound, so it favours proven high-volume performance over
              a lucky streak.
            </p>
          ) : (
            <p className="mt-2 text-muted">Best-player data is being collected.</p>
          )}
        </Card>

        {/* Related */}
        {related.length > 0 && (
          <div className="mt-10">
            <h2 className="mb-4 text-lg font-semibold">Other {c.role} champions</h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {related.map((r) => (
                <Link
                  key={r.slug}
                  href={`/champions/${r.slug}`}
                  className="glass glass-hover flex flex-col items-center gap-2 rounded-xl p-3 text-center"
                >
                  <ChampionAvatar champion={r} size={48} />
                  <span className="truncate text-sm font-medium">{r.name}</span>
                  <div className="flex items-center gap-1.5">
                    <TierChip tier={r.tier} />
                    <span className="text-xs font-semibold text-accent">{r.wr.toFixed(1)}%</span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}
      </Container>
    </>
  );
}

function Ability({ a }: { a: AbilityCard }) {
  const isPassive = a.key === "Passive";
  return (
    <div className="flex gap-3.5">
      <div className="relative shrink-0">
        {a.icon ? (
          <img src={a.icon} alt={a.name} width={48} height={48} className="rounded-lg ring-1 ring-white/10" />
        ) : (
          <span className="grid h-12 w-12 place-items-center rounded-lg bg-white/[0.06] text-sm font-bold text-faint">{a.key}</span>
        )}
        <span className={`absolute -left-1.5 -top-1.5 grid h-5 min-w-[20px] place-items-center rounded-full px-1 text-[0.6rem] font-bold ring-1 ring-line ${isPassive ? "bg-[#0e1322] text-gold" : "bg-[#0e1322] text-accent"}`}>
          {a.key}
        </span>
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-semibold">{a.name}</span>
          {a.cooldowns.length > 0 && (
            <span className="text-[0.7rem] text-faint">CD {a.cooldowns.join(" / ")}s</span>
          )}
          {a.damageTypes.map((d) => (
            <span key={d} className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[0.6rem] uppercase tracking-wide text-muted">{d}</span>
          ))}
        </div>
        {a.text && <p className="mt-1 text-sm leading-relaxed text-muted">{a.text}</p>}
      </div>
    </div>
  );
}

const BASE_STAT_ROWS: [string, string][] = [
  ["hp", "Health"], ["ad", "Attack Damage"], ["armor", "Armor"], ["mr", "Magic Resist"],
  ["attackSpeed", "Attack Speed"], ["moveSpeed", "Move Speed"], ["mana", "Mana"],
  ["hpRegen", "HP Regen (5s)"], ["manaRegen", "Mana Regen (5s)"],
];

function BaseStats({ stats }: { stats: Record<string, { base: number; perLevel: number; lvl15?: number }> }) {
  const rows = BASE_STAT_ROWS.filter(([k]) => stats[k]);
  const fmt = (n: number) => (Number.isInteger(n) ? n.toString() : n.toFixed(n < 3 ? 3 : 1));
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full min-w-[320px] text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-faint">
            <th className="pb-2 font-semibold">Stat</th>
            <th className="pb-2 text-right font-semibold">Level 1</th>
            <th className="pb-2 text-right font-semibold">Level 15</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([k, label]) => {
            const s = stats[k];
            const lvl15 = s.lvl15 ?? s.base + s.perLevel * 14;
            return (
              <tr key={k} className="border-t border-line/60">
                <td className="py-2 text-muted">{label}</td>
                <td className="py-2 text-right font-medium">{fmt(s.base)}</td>
                <td className="py-2 text-right font-medium text-accent">{fmt(lvl15)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Core items in purchase order, with the tier-2 boot placed where it's bought
 *  and the tier-3 upgrade shown after the item it lands on. */
function BuildOrder({ build }: { build: Build }) {
  const upAfter = build.bootsUpgradeAfter ?? 2;
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2.5">
      {build.bootsEarly && (
        <span className="inline-flex flex-col items-center">
          <img src={build.bootsEarly.icon} alt={build.bootsEarly.name} title={`${build.bootsEarly.name} (T2)`} width={40} height={40} className="rounded-lg ring-1 ring-white/10" />
          <span className="mt-0.5 text-[0.55rem] font-bold uppercase text-faint">T2 boots</span>
        </span>
      )}
      {build.coreBuild.map((it, i) => (
        <span key={it.slug} className="inline-flex items-center gap-2.5">
          <span className="relative" title={it.reason ? `${it.name} · ${it.reason}` : it.name}>
            <img src={it.icon} alt={it.name} width={46} height={46} className={`rounded-lg ${it.core ? "ring-2 ring-gold" : "ring-1 ring-white/10"}`} />
            <span className="absolute -left-1.5 -top-1.5 grid h-[18px] w-[18px] place-items-center rounded-full bg-[#0e1322] text-[0.6rem] font-bold text-accent ring-1 ring-line">{i + 1}</span>
          </span>
          {build.boots && build.bootsEarly && i + 1 === upAfter && (
            <span className="inline-flex flex-col items-center">
              <img src={build.boots.icon} alt={build.boots.name} title={`Upgrade to ${build.boots.name} (~10:00)`} width={40} height={40} className="rounded-lg ring-1 ring-gold/40" />
              <span className="mt-0.5 text-[0.55rem] font-bold uppercase text-gold">T3 @10:00</span>
            </span>
          )}
        </span>
      ))}
      {build.boots && !build.bootsEarly && (
        <>
          <span className="mx-0.5 text-faint">+</span>
          <span className="inline-flex flex-col items-center">
            <img src={build.boots.icon} alt={build.boots.name} title={build.boots.name} width={40} height={40} className="rounded-lg ring-1 ring-white/10" />
            <span className="mt-0.5 text-[0.55rem] font-bold uppercase text-faint">Boots</span>
          </span>
        </>
      )}
    </div>
  );
}

function Matchups({
  title,
  accent,
  champions,
}: {
  title: string;
  accent: string;
  champions: Champion[];
}) {
  return (
    <Card className="p-5">
      <h2 className={`text-sm font-semibold ${accent}`}>{title}</h2>
      {champions.length === 0 ? (
        <p className="mt-3 text-sm text-muted">No clear matchups tracked yet.</p>
      ) : (
        <div className="mt-3 flex flex-wrap gap-3">
          {champions.slice(0, 8).map((m) => (
            <Link
              key={m.slug}
              href={`/champions/${m.slug}`}
              className="group flex w-[52px] flex-col items-center gap-1 text-center"
            >
              <ChampionAvatar champion={m} size={44} showBadges={false} />
              <span className="w-full truncate text-[0.65rem] text-muted transition group-hover:text-text">
                {m.name}
              </span>
            </Link>
          ))}
        </div>
      )}
    </Card>
  );
}

function RegionStat({ label, wr, sub }: { label: string; wr?: number; sub?: string }) {
  if (wr == null) {
    return (
      <div className="glass rounded-xl p-4 text-center">
        <div className="text-xs font-bold uppercase tracking-wide text-faint">{label}</div>
        <div className="mt-2 text-sm text-faint">soon</div>
      </div>
    );
  }
  return (
    <div className="glass rounded-xl p-4 text-center">
      <div className="text-xs font-bold uppercase tracking-wide text-faint">{label}</div>
      <div className={`mt-1.5 text-2xl font-semibold ${wr >= 50 ? "text-accent" : "text-muted"}`}>
        {wr.toFixed(1)}%
      </div>
      {sub && <div className="mt-0.5 text-[0.7rem] leading-tight text-muted">{sub}</div>}
    </div>
  );
}
