"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  ALTERNATIVE_BUILD_VARIANT,
  buildChampions,
  buildForms,
  getBuildsFor,
  buildGold,
  visibleBuildVariants,
  type Build,
  type ChampionBuilds,
} from "@/lib/builds";
import { Tip } from "@/components/build-view";
import { ChampionAvatar, TierChip } from "@/components/ui";
import { EnemyBuildAdvisor, Sparkles, type Advice } from "@/components/enemy-build";
import { BuildCustomizer } from "@/components/build-customizer";
import { BuildStatsPanel, ChampionAbilitiesPanel } from "@/components/build-details";
import { DUAL_FORM_CHAMPIONS, hasSimulatableKit, ultTransform } from "@/lib/customizer-data";
import { BuildComparison, type ComparableBuild } from "@/components/build-comparison";
import { BuildExplanation } from "@/components/build-explanation";
import { BuildLikeButton } from "@/components/build-like";
import { ShareBuildButton } from "@/components/share-build";
import { AddToAlbumButton } from "@/components/add-to-album";
import { CounterBuilderCta, GenerateBuildCta } from "@/components/tool-crosslinks";
import { BuildTour, type TourStep } from "@/components/build-tour";
import { getChampions, pendingChampions } from "@/lib/data";
import { recommendedBuildsLive } from "@/lib/flags";

/* eslint-disable @next/next/no-img-element */

// "vs Enemy" moved to its own /counter page (the LLM advisor). The default
// build view is deliberately enemy-agnostic: standard/crit/dps/etc only.
const TABS = [
  {
    id: "recommended",
    label: "Recommended Builds",
    help: "Choose a playstyle to review a curated full build. Tap any item, rune, ability, or stat for an explanation, then open Compare Builds to check it against another playstyle.",
  },
  {
    id: "generate",
    label: "Personal Build Generator",
    help: "Choose your role, playstyle, and optimization goal, then generate. Review the recommendation and compare the result against any recommended build.",
  },
  {
    id: "customize",
    label: "Custom Build Lab",
    help: "Build from scratch or load a recommended starting point. Add or remove items and runes, inspect live stats, and compare your custom loadout before you commit to it.",
  },
] as const;
type Tab = (typeof TABS)[number]["id"];

const VARIANT_LABEL: Record<string, string> = {
  // Labels mirror the generator (scripts/build_champions_llm.py VARIANT_LABEL).
  // The stored ids never change; only the display name does.
  standard: "Standard", balanced: "Standard", damage: "Aggressive", dps: "Sustained DPS",
  oneshot: "One-shot", burst: "Burst", crit: "Crit", antitank: "Anti-tank",
  survivability: "Protective", tanky: "Durable", sustained: "Sustained",
  battlemage: "Battlemage", utility: "Utility", poke: "Poke",
  offmeta: "Alternative Path",
};

/** Legacy `offmeta` builds were generated under a forced-novelty prompt, so
 *  merely renaming them would make unreviewed builds look recommended. The
 *  stored id remains stable, but it is only exposed after the new generator (or
 *  a reviewer) explicitly approves the path. */

/** Only these exact path concepts can become identity-like UI. This deliberately
 *  does not read the model-authored top-level `damageProfile`: an incidental AP
 *  ratio must never turn a tank into an "AP bruiser" in the champion header. */
const CONTROLLED_PATH_LABELS: Record<string, string> = {
  tank: "Tank",
  bruiser: "Bruiser",
  "ad bruiser": "AD Bruiser",
  "ap bruiser": "AP Bruiser",
  "hybrid bruiser": "Hybrid Bruiser",
  "ad assassin": "AD Assassin",
  "ap assassin": "AP Assassin",
  "hybrid assassin": "Hybrid Assassin",
  "ad carry": "AD Carry",
  "ap carry": "AP Carry",
  "crit carry": "Crit Carry",
  "ad on hit": "AD On-hit",
  "ap on hit": "AP On-hit",
  "hybrid on hit": "Hybrid On-hit",
  lethality: "Lethality",
  battlemage: "Battlemage",
  enchanter: "Enchanter",
  utility: "Utility",
  "armor tank": "Armor Tank",
  "mixed resist tank": "Mixed-resist Tank",
  "engage tank": "Engage Tank",
  "physical spellblade bruiser": "Physical Spellblade Bruiser",
  "physical durable bruiser": "Physical Durable Bruiser",
  "physical duelist": "Physical Duelist",
  "physical spellblade duelist": "Physical Spellblade Duelist",
  "ap burst": "AP Burst",
  "crit duelist": "Crit Duelist",
  "hybrid ad + ap": "Hybrid AD + AP",
};

function controlledPathLabel(build: Build | null): string | null {
  const value = build?.pathLabel?.trim().toLowerCase().replaceAll("-", " ");
  return value ? CONTROLLED_PATH_LABELS[value] ?? null : null;
}

/** Mechanical archetype: HOW the kit delivers damage, which steers itemization
 *  (a weaver's cast-auto-cast rhythm makes Spellblade items core; an on-hit
 *  caster's abilities trigger on-hit items). Assigned per champion by
 *  scripts/assign_archetypes.py. */
const ARCHETYPE_LABEL: Record<string, string> = {
  spellcaster: "Spell-caster", autoattacker: "Auto-attacker",
  weaver: "Weaver", onhitcaster: "On-hit caster",
};

/**
 * Stands in for a champion's curated builds while they are still being checked.
 *
 * Deliberately a placeholder rather than a hidden tab: the tab is the promise,
 * and the two tools that ARE ready compute their answer live rather than
 * serving something pre-authored, so it points at those instead of dead-ending.
 */
function RecommendedComingSoon({ name, onGenerate }: { name: string; onGenerate: () => void }) {
  return (
    <div className="glass rounded-2xl p-6 text-center sm:p-8">
      <span className="inline-flex rounded-full bg-gold/15 px-3 py-1 text-xs font-bold uppercase tracking-wide text-gold">
        Coming soon
      </span>
      <h3 className="mt-3 text-lg font-semibold">Curated builds for {name} are still in review</h3>
      <p className="mx-auto mt-2 max-w-lg text-sm leading-relaxed text-muted">
        Every recommended build is checked before it ships, and {name} has not been through that
        pass yet. Nothing here is hidden because it is broken -- it is hidden because it has not
        been verified, and a build you cannot trust is worse than no build.
      </p>
      <p className="mx-auto mt-3 max-w-lg text-sm leading-relaxed text-muted">
        The Personal Build Generator works for {name} right now and builds around how you play.
        The Custom Build Lab is open too, with live stats for anything you assemble.
      </p>
      <button
        onClick={onGenerate}
        className="mt-5 inline-flex rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black transition hover:opacity-90"
      >
        Generate a build for {name} →
      </button>
    </div>
  );
}

export function BuildStudio({ initialChampion, initialTab, initialVariant }: {
  initialChampion?: string; initialTab?: Tab; initialVariant?: string;
} = {}) {
  const champs = useMemo(() => {
    const built = new Map(buildChampions().map((entry) => [entry.slug, entry]));
    // Champions with no leaderboard yet are excluded from every ranking, but
    // their kit and their generated build are real, so the studio lists the
    // ones that actually have a build to show.
    const pendingWithBuilds = pendingChampions()
      .map((champion) => ({ champion, builds: getBuildsFor(champion.name) }))
      .filter((entry) => entry.builds && hasSimulatableKit(entry.champion.name))
      .map((entry) => ({ slug: entry.champion.slug, champion: entry.champion, builds: entry.builds! }));
    return [...getChampions(), ...pendingWithBuilds.map((e) => e.champion)].map((champion) =>
      built.get(champion.slug)
        ?? pendingWithBuilds.find((e) => e.slug === champion.slug)
        ?? { slug: champion.slug, champion, builds: null },
    );
  }, []);
  const initialSlug = champs.some((entry) => entry.slug === initialChampion) ? initialChampion! : champs[0]?.slug ?? "";
  const initialRecord = champs.find((entry) => entry.slug === initialSlug);
  const [slug, setSlug] = useState(initialSlug);
  const [tab, setTab] = useState<Tab>(initialTab ?? (initialRecord?.builds ? "recommended" : "generate"));
  const [generatedAdvice, setGeneratedAdvice] = useState<Advice | null>(null);
  const [champQuery, setChampQuery] = useState("");

  const rec = champs.find((c) => c.slug === slug) ?? champs[0];
  // Kayn transforms permanently into one of two kits that want opposite items,
  // so each has its own generated build set and the studio picks between them.
  const forms = useMemo(() => buildForms(rec.champion.name), [rec.champion.name]);
  const [formKeyState, setFormKey] = useState("base");
  const form = forms.find((f) => f.key === formKeyState) ?? forms[0] ?? null;
  const builds = form ? form.builds : rec.builds;
  // The engine simulates the FORM, not the champion: pricing Rhaast's build
  // against Shadow Assassin's kit is the mismatch this whole split removes.
  const engineName = form && form.key !== "base" ? form.key : rec.champion.name;
  const archetype = (builds as (ChampionBuilds & {
    archetype?: { archetype?: string; reason?: string };
  }) | null)?.archetype;
  const variants = builds ? visibleBuildVariants(builds) : [];
  const [variantState, setVariant] = useState(
    (initialVariant && variants.includes(initialVariant) ? initialVariant : undefined)
      ?? variants.find((v) => v === "standard" || v === "balanced")
      ?? variants[0]
      ?? "",
  );
  const variant = builds ? (variants.includes(variantState) ? variantState : variants[0]) : "";
  const build = builds && variant ? builds.builds[variant] : null;

  const name = rec.champion.name;

  // The curated catalogue is still being validated, so Recommended Builds is
  // open per champion. The tab stays visible either way -- a locked tab that
  // says what is coming reads better than a tab that silently is not there.
  const recommendedOpen = recommendedBuildsLive(rec.champion.name);
  // Two different controls, and most champions have neither: the header toggle
  // that swaps between separately generated build sets (Kayn), and the panel
  // toggle that re-reads stats and abilities in the transformed state.
  const tours = tabTours({
    formSets: forms.length > 1,
    transforms: Boolean(ultTransform(engineName)) || Boolean(DUAL_FORM_CHAMPIONS[engineName]),
    generated: Boolean(generatedAdvice && !generatedAdvice.error),
  });
  // Comparisons expose the same curated item lists, so they follow the gate.
  const comparisonChoices = builds && recommendedOpen
    ? variants.map((key) => comparableFromBuild(key, builds.builds[key]))
    : [];
  const availableTabs = builds ? TABS : TABS.filter((entry) => entry.id === "generate");
  const wanted = availableTabs.some((entry) => entry.id === tab) ? tab : "generate";
  const effectiveTab = wanted === "recommended" && !recommendedOpen ? "recommended" : wanted;
  const selectedPathLabel = effectiveTab === "recommended" ? controlledPathLabel(build) : null;

  const switchChamp = (s: string) => {
    setSlug(s);
    setFormKey("base");
    const next = champs.find((entry) => entry.slug === s);
    setTab(next?.builds && recommendedBuildsLive(next.champion.name) ? "recommended" : "generate");
    setGeneratedAdvice(null);
  };
  const filteredChamps = champQuery
    ? champs.filter((c) => c.champion.name.toLowerCase().includes(champQuery.toLowerCase()))
    : champs;

  return (
    <div>
      {/* One tour per tab, not one for the studio. Each tab is a different
          tool with different controls, and a single walkthrough could only ever
          describe the tab that happened to be open. Keying by tab remounts the
          tour, so opening a tab for the first time starts its own -- and a tab
          already seen stays quiet. */}
      <BuildTour
        key={effectiveTab}
        storageKey={tours[effectiveTab].storageKey}
        steps={tours[effectiveTab].steps}
        label="Tour"
      />
      {/* champion search + selector strip */}
      <input
        value={champQuery}
        onChange={(e) => setChampQuery(e.target.value)}
        placeholder="Search champion…"
        data-tour="champion-search"
        className="mb-2 w-full max-w-xs rounded-lg border border-line bg-white/[0.04] px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
      />
      <div data-tour="champion-strip" className="-mx-1 flex gap-1.5 overflow-x-auto pb-2">
        {filteredChamps.map((c) => (
          <button
            key={c.slug}
            onClick={() => switchChamp(c.slug)}
            className={`shrink-0 rounded-full p-0.5 transition ${c.slug === slug ? "ring-2 ring-accent" : "opacity-60 hover:opacity-100"}`}
            title={c.champion.name}
          >
            <ChampionAvatar champion={c.champion} size={44} showBadges={false} />
          </button>
        ))}
        {filteredChamps.length === 0 && <span className="py-3 text-sm text-faint">No champion matches.</span>}
      </div>

      {/* champion header with splash-art banner */}
      <div className="relative mt-3 overflow-hidden rounded-2xl border border-line">
        {rec.champion.splash && (
          <>
            <img src={rec.champion.splash} alt="" aria-hidden className="absolute inset-0 h-full w-full object-cover object-top opacity-30" />
            <div className="absolute inset-0 bg-gradient-to-r from-[#070a12] via-[#070a12]/80 to-transparent" />
          </>
        )}
        <div className="relative flex flex-wrap items-center gap-3 p-4">
          {/* The banner icon opens the champion's own page. */}
          <Link href={`/champions/${rec.slug}`} title={`Open ${name}'s champion page`} className="shrink-0 rounded-full transition hover:ring-2 hover:ring-accent/60">
            <ChampionAvatar champion={rec.champion} size={60} showBadges={false} />
          </Link>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-bold">{name}</h2>
              <TierChip tier={rec.champion.tier} />
              {archetype?.archetype && (
                <Tip tip={<><span className="font-bold">{ARCHETYPE_LABEL[archetype.archetype] ?? archetype.archetype}</span>{archetype.reason && <span className="mt-1 block text-muted">{archetype.reason}</span>}</>}>
                  <span className="cursor-pointer rounded-md bg-gold/15 px-2 py-0.5 text-xs font-semibold text-gold">{ARCHETYPE_LABEL[archetype.archetype] ?? archetype.archetype}</span>
                </Tip>
              )}
            </div>
            <p className="text-sm text-muted">
              {builds?.class ?? rec.champion.class} · {builds?.role ?? rec.champion.role}
              {selectedPathLabel ? ` · ${selectedPathLabel}` : ""}
            </p>
          </div>
          {/* Transform toggle. Kayn commits to one of these for the rest of the
              game and they want opposite items, so the whole tab -- build,
              stats, customizer and generation -- follows the choice. */}
          {forms.length > 1 && (
            <div data-tour="champion-form" className="ml-auto flex gap-1 rounded-xl border border-line bg-black/30 p-1">
              {forms.map((f) => {
                const active = f.key === (form?.key ?? "base");
                const red = f.key !== "base";
                return (
                  <button
                    key={f.key}
                    onClick={() => setFormKey(f.key)}
                    title={`${f.label} — its own items, runes and simulated damage`}
                    className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${
                      active
                        ? red ? "bg-red-400/20 text-red-300" : "bg-sky-400/20 text-sky-300"
                        : "text-muted hover:text-text"
                    }`}
                  >
                    <span className="block">{f.label}</span>
                    <span className="block text-[0.6rem] font-normal opacity-75">{f.shortLabel}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* tabs */}
      <div data-tour="tabs" className="mt-4 flex gap-1 overflow-x-auto rounded-xl border border-line bg-white/[0.03] p-1">
        {availableTabs.map((entry) => (
          <button
            key={entry.id}
            onClick={() => setTab(entry.id)}
            title={entry.help}
            className={`flex-1 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-semibold transition ${effectiveTab === entry.id ? "bg-accent/20 text-accent" : "text-muted hover:text-text"}`}
          >
            {entry.label}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {effectiveTab === "recommended" && !recommendedOpen && <RecommendedComingSoon name={name} onGenerate={() => setTab("generate")} />}
        {effectiveTab === "recommended" && recommendedOpen && build && (
          <BuildTab {...{ variants, variant, setVariant, build, name, engineName, slug, comparisonChoices }} onGenerate={() => setTab("generate")} />
        )}
        {effectiveTab === "generate" && (
          <GenerateTab
            key={`${name}:${form?.key ?? "base"}`}
            name={name}
            championForm={form ? (form.key === "base" ? "shadow-assassin" : "rhaast") : undefined}
            advice={generatedAdvice}
            setAdvice={setGeneratedAdvice}
            comparisonChoices={comparisonChoices}
          />
        )}
        {effectiveTab === "customize" && builds && <BuildCustomizer name={engineName} data={builds} comparisonChoices={comparisonChoices} />}
      </div>

      {/* Hand-off to the other tool: this page never looks at the enemy team. */}
      <div className="mt-6" data-tour="counter-cta">
        <CounterBuilderCta champion={name} />
      </div>
    </div>
  );
}

/** The two panels every tab shows once there is a build on screen. They are the
 *  reason to trust the rest of the page, and the tour never mentioned them. */
const statSteps = (transforms: boolean): TourStep[] => [
  {
    target: "build-stats",
    title: "Champion stats, not item stats",
    body: "This is the whole build resolved onto the champion at level 15: base growth, every item and the guaranteed part of the runes, with kit conversions already applied. Guaranteed is what you are certain to have when a fight starts; Fully scaled is what the loadout is worth once stacking items and ramping passives have paid off. The gap between the two is how greedy a build is."
      + (transforms ? " This champion transforms, so the toggle beside it reads the stats in either state." : ""),
  },
  {
    target: "ability-values",
    title: "What your abilities actually hit for",
    body: "Every ability recalculated against those stats -- real numbers, not ratios. Tap one for the formula, the rank it is read at, and the cooldown after haste."
      + (transforms
        ? " The toggle here switches the whole panel to the transformed kit, so you can read the abilities and damage you actually get after transforming."
        : ""),
  },
];

/** Per-tab walkthroughs. Bump a storageKey when its tab changes shape enough
 *  that the old walkthrough would be describing controls that moved. */
const studioTour = ({ formSets, transforms }: TourContext): TourStep[] => [
  {
    target: "champion-search",
    title: "Start with your champion",
    body: "Search, or scroll the portrait strip. Everything below re-reads from the champion you pick.",
  },
  {
    target: "tabs",
    title: "Three tabs, three questions",
    body: "Recommended Builds is the curated answer, the Personal Build Generator builds around how you play, and the Custom Build Lab lets you assemble your own and see the stats move.",
  },
  {
    target: "build-order",
    title: "The build order, explained",
    body: "Items are shown in purchase order, with boots slotted where they actually get bought. Tap any item, rune or ability for the reasoning behind it.",
  },
  ...(formSets ? [{
    target: "champion-form",
    title: "This champion gets two separate builds",
    body: "Kayn commits to Shadow Assassin or Rhaast for the rest of the game, and they want opposite items, so each form has its own build. The toggle switches everything below it: items, runes, stats and the simulated damage.",
  }] : []),
  ...statSteps(transforms),
  {
    target: "generate-cta",
    title: "Nothing here fits your game?",
    body: "Generate a build around your role, playstyle and power spike, then compare it against any recommended build.",
  },
  {
    target: "counter-cta",
    title: "Facing a specific enemy team?",
    body: "The Counter Builder rebuilds your items and runes around the exact five champions you are up against.",
  },
];

/** What the open champion actually puts on screen. The tour describes only
 *  what is there: a step whose target does not exist still renders, just with
 *  nothing highlighted, and a walkthrough pointing at a control the player
 *  cannot see is worse than no step at all. */
type TourContext = { formSets: boolean; transforms: boolean; generated: boolean };

const tabTours = (ctx: TourContext): Record<Tab, { storageKey: string; steps: TourStep[] }> => ({
  recommended: { storageKey: "wtm_tour_studio_v2", steps: studioTour(ctx) },
  generate: {
    storageKey: "wtm_tour_generate_v2",
    steps: [
      {
        target: "your-champion",
        title: "This build is about you, not the enemy",
        body: "The generator ignores who you are against on purpose. It builds around how you want to play the champion; the Counter Builder is the one that reads the enemy team.",
      },
      {
        target: "playstyle",
        title: "Pick the playstyle you actually want",
        body: "Not every champion offers every option: the list is filtered to the playstyles that champion can genuinely support, so anything you can choose here is a real build path.",
      },
      {
        target: "role",
        title: "Where are you actually playing it?",
        body: "The role changes the build, not just the label: a jungler and a baron laner want different first items on the same champion. Pick something the champion is not normally played in and it warns you rather than quietly building something odd.",
      },
      {
        target: "objective",
        title: "Optimize for the job you need doing",
        body: "This is what the build is being solved FOR -- carrying a fight, surviving a dive, shredding tanks, or a balanced spread. It moves the item priorities rather than reshuffling the same list.",
      },
      {
        target: "power-spike",
        title: "Say when you want to be strong",
        body: "Early, mid, late or balanced. This changes the purchase order more than the item list, because in a 15-20 minute game when an item lands matters as much as which item it is.",
      },
      {
        target: "locks",
        optional: true,
        title: "Force in an item or rune you insist on",
        body: "Pin up to three items and two runes and the build has to include them. Most players never need this; it is here for when you already know one piece of the build and want the generator to solve the rest around it. Leave it closed and nothing changes.",
      },
      {
        target: "generate",
        title: "Generate, then read the reasoning",
        body: "You get a full item order, boot timing, runes, situational swaps and a rating for the finished build. It takes about 30 seconds. Save anything worth keeping to an album. The champion stats and live ability values appear underneath once it finishes, so you can see what the build is actually worth before you trust it.",
      },
      // The stat panels only exist after a generation. Adding their steps
      // before that would spotlight nothing, which is the thing this tour was
      // getting wrong; once a build is on screen they are worth explaining.
      ...(ctx.generated ? statSteps(ctx.transforms) : []),
    ],
  },
  customize: {
    storageKey: "wtm_tour_lab_v2",
    steps: [
      {
        target: "lab-start-from",
        title: "Start from scratch, or from something that works",
        body: "An empty board is a slow start. Load a recommended build here and edit from there, or clear it and pick every slot yourself.",
      },
      {
        target: "lab-slots",
        title: "Five items, boots, and a full rune page",
        body: "Tap an empty slot to pick, tap the small cross to remove. Items, boots, keystone and the three minors all behave the same way.",
      },
      ...statSteps(ctx.transforms),
      {
        target: "lab-saved",
        title: "Save what you land on",
        body: "Custom builds are kept on this device, up to 20 of them, and can be compared against each other or against any recommended build. Signed in, you can file them into an album instead.",
      },
    ],
  },
});


/* eslint-disable @typescript-eslint/no-explicit-any */
/** A boots tile in the build order, badged with its tier. Patch 7.2 turned the
 *  tier-3 boot into a real purchase (2000-2200g, unlocked at 10:00), so the
 *  order has to show WHICH boot you hold and WHEN it upgrades. */
function BootTile({ it, tier, note }: { it: any; tier?: string; note?: string }) {
  return (
    <Tip
      tip={
        <>
          <span className="font-bold">{it.name}</span>
          <span className="text-gold"> · {(it.cost || 0).toLocaleString()}g</span>
          {note && <span className="mt-1 block text-accent">{note}</span>}
        </>
      }
    >
      <span className="relative cursor-pointer">
        <img src={it.icon} alt={it.name} width={40} height={40} className="rounded-lg ring-1 ring-white/10" />
        {tier && (
          <span className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 rounded bg-[#0e1322] px-1 text-[0.55rem] font-bold uppercase leading-tight text-faint ring-1 ring-line">
            {tier}
          </span>
        )}
      </span>
    </Tip>
  );
}

function BuildTab({ variants, variant, setVariant, build, name, engineName, slug, onGenerate, comparisonChoices }: any) {
  const finalItemSlugs = [
    ...build.coreBuild.map((item: { slug: string }) => item.slug),
    ...(build.boots?.slug ? [build.boots.slug] : []),
  ];
  return (
    <div className="flex flex-col gap-4">
      {/* Recommended builds are created without an enemy team. The callout says
          so and links straight into the Counter Builder for this champion, so
          nobody mistakes a curated build for a matchup-tuned one. */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line/60 bg-white/[0.02] px-3 py-2.5">
        <p className="text-xs leading-relaxed text-muted">
          Recommended builds are created <span className="text-text">without knowing the enemy team</span>.
          For a build tuned to the matchup, use the Counter Builder.
        </p>
        <Link
          href={`/counter?champion=${encodeURIComponent(name)}`}
          className="shrink-0 rounded-lg bg-emerald-400/15 px-3 py-1.5 text-xs font-bold text-emerald-300 transition hover:bg-emerald-400/25"
        >
          Build Against Enemy Team →
        </Link>
      </div>

      {/* Variant pills + the AI "generate my build" button. Studio mode is a
          personal, enemy-agnostic build; Counter Builder handles matchups. */}
      <div className="flex flex-wrap items-center gap-1.5">
        {variants.map((v: string) => {
          const alternative = v === ALTERNATIVE_BUILD_VARIANT;
          const active = v === variant;
          return (
            <button
              key={v}
              onClick={() => setVariant(v)}
              title={alternative
                ? "A reviewed secondary build path supported by this champion's repeated combat pattern"
                : `Show the ${VARIANT_LABEL[v] ?? v} recommended build`}
              className={`rounded-lg px-3 py-1.5 text-sm font-semibold transition ${
                active
                  ? alternative ? "bg-violet-400/20 text-violet-200" : "bg-accent/20 text-accent"
                  : alternative ? "bg-violet-400/[0.08] text-violet-200/80 hover:text-violet-200" : "bg-white/[0.04] text-muted hover:text-text"
              }`}
            >
              {VARIANT_LABEL[v] ?? v}
            </button>
          );
        })}
        <button onClick={onGenerate} title="Open the Personal Build Generator for this champion"
                className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-bold text-black transition hover:opacity-90">
          <Sparkles />
          Generate my build
        </button>
        <span className="ml-auto self-center rounded-md bg-gold/10 px-2 py-1 text-xs font-semibold text-gold">~{buildGold(build).toLocaleString()}g</span>
      </div>

      {variant === ALTERNATIVE_BUILD_VARIANT && (
        <div className="rounded-xl border border-violet-400/30 bg-violet-400/[0.07] p-4">
          <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-violet-200">
            <span className="rounded bg-violet-400/20 px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide">
              Alternative Path
            </span>
            A supported secondary way to build {name}
          </p>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            This path is only shown after its items and runes have been reviewed against the champion&apos;s
            repeated combat pattern. It is distinct from the default path, but it is not novelty built from one incidental ratio.
          </p>
          {build.summary && <p className="mt-2 text-sm leading-relaxed text-text/90">{build.summary}</p>}
        </div>
      )}

      {/* Reactions: liking and sharing are only offered on the curated builds,
          which are the ones that are stable enough to be worth a public vote. */}
      <div className="flex flex-wrap items-center gap-2">
        <BuildLikeButton buildId={`${slug}:${variant}`} />
        <ShareBuildButton
          path={`/build?champion=${encodeURIComponent(slug)}&variant=${encodeURIComponent(variant)}`}
          title={`${name} ${VARIANT_LABEL[variant] ?? variant} build`}
          text={`${name} ${VARIANT_LABEL[variant] ?? variant} build on WrTrueMeta: full item order, boots timing and runes.`}
        />
        <AddToAlbumButton
          build={{
            champion: name,
            championSlug: slug,
            source: "recommended",
            variant,
            items: finalItemSlugs,
            runes: runeNamesFromBuild(build),
          }}
        />
      </div>

      {/* the build: items */}
      <div data-tour="build-order" className="glass rounded-2xl p-4">
        <p className="mb-3 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Build order <span className="normal-case text-faint/60">· tap for details{build.bootsEarly ? " · T2 boots first, T3 upgrade at 10:00" : ""}</span></p>
        {/* Boots sit IN the order, not appended after it: 7.2 made tier 3 a real
            2000-2200g purchase unlocked at 10:00, so you buy tier 2 first and
            upgrade a couple of items later. */}
        <div className="flex flex-wrap items-center gap-2.5">
          {build.bootsEarly && (
            <BootTile it={build.bootsEarly} tier="T2" />
          )}
          {build.coreBuild.map((it: any, i: number) => (
            <span key={it.slug} className="inline-flex items-center gap-2.5">
              <Tip tip={<><span className="font-bold">{it.name}</span><span className="text-gold"> · {it.cost.toLocaleString()}g</span>{it.core && <span className="ml-1 rounded bg-gold/20 px-1 text-[0.6rem] font-bold uppercase text-gold">core</span>}{it.reason && <span className="mt-1 block text-muted">{it.reason}</span>}</>}>
                <span className="relative cursor-pointer">
                  <img src={it.icon} alt={it.name} width={46} height={46} className={`rounded-lg ${it.core ? "ring-2 ring-gold" : "ring-1 ring-white/10"}`} />
                  <span className="absolute -left-1.5 -top-1.5 grid h-4.5 w-4.5 min-h-[18px] min-w-[18px] place-items-center rounded-full bg-[#0e1322] text-[0.6rem] font-bold text-accent ring-1 ring-line">{i + 1}</span>
                </span>
              </Tip>
              {build.boots && build.bootsEarly && build.bootsUpgradeAfter === i + 1 && (
                <BootTile it={build.boots} tier="T3" note={`Upgrade from ${build.bootsEarly.name} after item ${i + 1} (unlocks at 10:00)`} />
              )}
            </span>
          ))}
          {/* no tier-3 for these boots: show them once, at the end */}
          {build.boots && !build.bootsEarly && (
            <>
              <span className="mx-0.5 text-faint">+</span>
              <BootTile it={build.boots} />
            </>
          )}
        </div>

        {/* runes + summoners */}
        <div className="mt-4 flex flex-wrap items-center gap-4 border-t border-line/60 pt-3">
          <div className="flex items-center gap-2">
            {build.runes.keystone && <Tip tip={<span className="font-bold">{build.runes.keystone.name}</span>}><img src={build.runes.keystone.icon} alt="" width={38} height={38} className="cursor-pointer rounded-full ring-1 ring-white/15" /></Tip>}
            {build.runes.treeMinors.map((r: any) => (
              <Tip key={r.name} tip={<span className="font-bold">{r.name}</span>}><img src={r.icon} alt="" width={28} height={28} className="cursor-pointer rounded-full ring-1 ring-white/10" /></Tip>
            ))}
            {build.runes.flexMinor && <Tip tip={<span className="font-bold">{build.runes.flexMinor.name}</span>}><img src={build.runes.flexMinor.icon} alt="" width={28} height={28} className="cursor-pointer rounded-full opacity-90 ring-1 ring-white/10" /></Tip>}
          </div>
          {(build.summoners ?? []).length > 0 && (
            <div className="flex items-center gap-2">
              {build.summoners.map((s: any) => (
                <Tip key={s.name} tip={<span className="font-bold">{s.name}</span>}><img src={s.icon} alt={s.name} width={28} height={28} className="cursor-pointer rounded-md ring-1 ring-white/10" /></Tip>
              ))}
            </div>
          )}
        </div>
      </div>

      <SituationalPanel build={build} />

      <BuildExplanation build={build} />

      <BuildStatsPanel name={engineName ?? name} itemSlugs={finalItemSlugs} runeNames={runeNamesFromBuild(build)} level={15} />
      <ChampionAbilitiesPanel
        name={engineName ?? name}
        itemSlugs={finalItemSlugs}
        runeNames={runeNamesFromBuild(build)}
        level={15}
      />
      <BuildComparison
        champion={engineName ?? name}
        current={comparableFromBuild(variant, build)}
        choices={comparisonChoices}
      />

      <div data-tour="generate-cta">
        <GenerateBuildCta champion={name} onGenerate={onGenerate} />
      </div>
    </div>
  );
}

const ORDINALS = ["", "1st", "2nd", "3rd", "4th", "5th"];

/** Situational swaps for a curated build.
 *
 *  A swap is only useful if you know WHEN it happens: it is bought in place of
 *  the item at that position, not bolted onto the end of the build. Swaps are
 *  therefore ordered by purchase position and labelled with it. */
function SituationalPanel({ build }: { build: Build }) {
  const swaps = [...(build.situational ?? [])].sort(
    (left, right) => (left.atPosition ?? 9) - (right.atPosition ?? 9),
  );
  const runeSwaps = build.situationalRunes ?? [];
  if (swaps.length === 0 && runeSwaps.length === 0) return null;

  return (
    <div className="glass rounded-2xl p-4">
      <p className="mb-3 text-[0.65rem] font-bold uppercase tracking-wide text-faint">
        Situational swaps <span className="normal-case text-faint/60">· bought in place of that purchase</span>
      </p>
      <div className="flex flex-col gap-2">
        {swaps.map((swap) => (
          <div key={`${swap.slug}-${swap.replaces}`} className="flex flex-wrap items-center gap-2 text-sm">
            {swap.atPosition && (
              <span className="shrink-0 rounded-md bg-accent/15 px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide text-accent">
                {ORDINALS[swap.atPosition] ?? `${swap.atPosition}th`} item
              </span>
            )}
            <img src={swap.icon} alt={swap.name} width={26} height={26} className="rounded ring-1 ring-white/10" />
            <span className="font-medium">{swap.name}</span>
            <span className="text-muted">
              {swap.replaces && (() => {
                const replaced = build.coreBuild.find((item) => item.slug === swap.replaces);
                return replaced ? `instead of ${replaced.name}` : "";
              })()}{" "}
              {swap.when ? `· ${swap.when}` : ""}
            </span>
          </div>
        ))}
        {runeSwaps.map((swap) => (
          <div key={swap.slug} className="flex flex-wrap items-center gap-2 text-sm">
            <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide ${
              swap.replacesType === "item" ? "bg-gold/15 text-gold" : "bg-violet-400/15 text-violet-300"
            }`}>
              {swap.replacesType === "item" ? "frees an item" : "rune"}
            </span>
            <img src={swap.icon} alt={swap.name} width={26} height={26} className="rounded-full ring-1 ring-white/10" />
            <span className="font-medium">{swap.name}</span>
            <span className="text-muted">
              {swap.replacesLabel ? `over ${swap.replacesLabel}` : ""} {swap.when ? `· ${swap.when}` : ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function GenerateTab({
  name,
  championForm,
  advice,
  setAdvice,
  comparisonChoices,
}: {
  name: string;
  championForm?: string;
  advice: Advice | null;
  setAdvice: (advice: Advice | null) => void;
  comparisonChoices: ComparableBuild[];
}) {
  const itemSlugs = advice && !advice.error
    ? [...(advice.items ?? []), ...(advice.bootsUpgrade ? [advice.bootsUpgrade] : advice.boots ? [advice.boots] : [])]
    : [];
  const runeNames = advice?.runes
    ? [advice.runes.keystone, ...advice.runes.minors, advice.runes.flex].filter(Boolean)
    : [];

  return (
    <div className="flex flex-col gap-4">
      <EnemyBuildAdvisor presetChampion={name} presetForm={championForm} mode="studio" onAdviceChange={setAdvice} />
      {itemSlugs.length > 0 && (
        <>
          <BuildStatsPanel name={name} itemSlugs={itemSlugs} runeNames={runeNames} level={15} />
          <ChampionAbilitiesPanel name={name} itemSlugs={itemSlugs} runeNames={runeNames} level={15} />
          <BuildComparison
            champion={name}
            current={{ id: "generated", label: "Generated build", itemSlugs, runeNames }}
            choices={comparisonChoices}
          />
        </>
      )}
    </div>
  );
}

function runeNamesFromBuild(build: Build): string[] {
  return [
    build.runes.keystone?.name,
    ...build.runes.treeMinors.map((rune) => rune.name),
    build.runes.flexMinor?.name,
  ].filter((name): name is string => Boolean(name));
}

function comparableFromBuild(key: string, build: Build): ComparableBuild {
  return {
    id: `recommended:${key}`,
    label: `${VARIANT_LABEL[key] ?? key} build`,
    itemSlugs: [
      ...build.coreBuild.map((item) => item.slug),
      ...(build.boots?.slug ? [build.boots.slug] : []),
    ],
    runeNames: runeNamesFromBuild(build),
  };
}

/* Retired simulator UI kept temporarily for reference; no engine-derived
 * analysis is rendered or executed in Build Studio.
function analysisWin(build: any): number | undefined {
  return build?.analysis?.winScore;
}

const BEHAVIOR_ROWS: { key: string; label: string }[] = [
  { key: "spellCastRate", label: "Spell cast rate" },
  { key: "fightFrequency", label: "Fight frequency" },
  { key: "tradeFrequency", label: "Trade frequency" },
  { key: "avgFightLength", label: "Fight length" },
  { key: "objectiveDamage", label: "Objective damage" },
  { key: "waveclear", label: "Waveclear" },
  { key: "jungleClear", label: "Jungle clear" },
  { key: "roamFrequency", label: "Roam frequency" },
];

function BehaviorPanel({ name }: { name: string }) {
  const b = championBehavior(name);
  if (!b) return null;
  const stars = (v?: number) => "★★★★★".slice(0, Math.round((v ?? 0) * 5)).padEnd(5, "☆");
  return (
    <div className="glass rounded-2xl p-4">
      <p className="mb-3 text-[0.65rem] font-bold uppercase tracking-wide text-faint">
        Playstyle profile <span className="normal-case text-faint/60">· how {name} plays, drives item value</span>
      </p>
      <div className="grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
        {BEHAVIOR_ROWS.filter((r) => (b as any)[r.key] != null).map((r) => (
          <div key={r.key} className="flex items-center justify-between text-sm">
            <span className="text-muted">{r.label}</span>
            <span className="tracking-widest text-gold">{stars((b as any)[r.key])}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AnalysisTab({ analysis, m, level, setLevel, name }: any) {
  return (
    <div className="flex flex-col gap-4">
      <LevelSlider level={level} setLevel={setLevel} />
      {analysis && <SimReadout a={analysis} />}
      <BehaviorPanel name={name} />
      base stats
      {m && (
        <div className="glass rounded-2xl p-4">
          <p className="mb-3 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Champion stats <span className="normal-case text-faint/60">· at level {level}, with this build</span></p>
          <div className="grid grid-cols-3 gap-x-2 gap-y-3 text-center sm:grid-cols-5">
            <Stat label="Attack Damage" v={m.ad} cls="text-orange-400" />
            <Stat label="Ability Power" v={m.ap} cls="text-violet-400" />
            <Stat label="Health" v={m.hp.toLocaleString()} cls="text-emerald-300" />
            <Stat label="Armor" v={m.armor} cls="text-orange-300" />
            <Stat label="Magic Resist" v={m.mr} cls="text-violet-300" />
            <Stat label="Attack Speed" v={m.attackSpeed} cls="text-text" />
            <Stat label="Crit" v={`${m.crit}%`} cls="text-gold" />
            <Stat label="Ability Haste" v={m.haste} cls="text-accent" />
            <Stat label="Move Speed" v={m.moveSpeed} cls="text-text" />
            <Stat label="Mana" v={m.mana.toLocaleString()} cls="text-blue-300" />
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, v, cls }: { label: string; v: string | number; cls: string }) {
  return (
    <div>
      <div className={`text-lg font-bold ${cls}`}>{v}</div>
      <div className="text-[0.55rem] uppercase tracking-wide text-faint">{label}</div>
    </div>
  );
}
*/
