"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  buildChampions,
  buildForms,
  getBuildsFor,
  visibleBuildVariants,
  formEngineName,
  type Build,
  type ChampionBuilds,
} from "@/lib/builds";
import { Tip } from "@/components/build-view";
import { ChampionAvatar, TierChip } from "@/components/ui";
import { EnemyBuildAdvisor, type Advice } from "@/components/enemy-build";
import { BuildCustomizer, labSeedFromFlat, type CustomBuildState as LabSeed } from "@/components/build-customizer";
import { BuildStatsPanel, ChampionAbilitiesPanel } from "@/components/build-details";
import { DUAL_FORM_CHAMPIONS, hasSimulatableKit, ultTransform } from "@/lib/customizer-data";
import { BuildComparison, type ComparableBuild } from "@/components/build-comparison";
import { BuildFeedback } from "@/components/build-feedback";
import { track } from "@/components/share-build";
import { CounterBuilderCta, GenerateBuildCta } from "@/components/tool-crosslinks";
import { BuildTour, type TourStep } from "@/components/build-tour";
import { getChampions, pendingChampions } from "@/lib/data";
import { recommendedBuildsLive } from "@/lib/flags";

/* eslint-disable @next/next/no-img-element */

// The two generators sit side by side because they answer the same question
// with different inputs: one reads how you want to play, the other reads who
// you are up against. "Counter Builder" lived on its own /counter page and was
// the least-found tool on the site -- 110 visits against the tier list's 498 --
// which is what a second page for a second half of one question earns. The
// name went with it: nothing in "Counter Builder" says enemy team.
//
// The curated Recommended Builds tab used to hold the first slot. That
// catalogue is retired, so the slot went to the tool people could not find.
const TABS = [
  {
    id: "generate",
    label: "Personal Build Generator",
    shortLabel: "Generate",
    help: "Choose your role, playstyle, and optimization goal, then generate the optimal build around how you want to play. This one ignores the enemy team on purpose.",
  },
  {
    id: "counter",
    label: "Build vs Enemy Team",
    shortLabel: "vs Enemy Team",
    help: "Name the five champions you are up against and get the build that beats exactly those picks: items, purchase order, boots and runes, with what it can and cannot answer.",
  },
  {
    id: "customize",
    label: "Custom Build Lab",
    shortLabel: "Custom Lab",
    help: "Build from scratch or load a generated build. Add or remove items and runes, inspect live stats, and compare your custom loadout before you commit to it.",
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

/** Mechanical archetype: HOW the kit delivers damage, which steers itemization
 *  (a weaver's cast-auto-cast rhythm makes Spellblade items core; an on-hit
 *  caster's abilities trigger on-hit items). Assigned per champion by
 *  scripts/assign_archetypes.py. */
const ARCHETYPE_LABEL: Record<string, string> = {
  spellcaster: "Spell-caster", autoattacker: "Auto-attacker",
  weaver: "Weaver", onhitcaster: "On-hit caster",
};

export function BuildStudio({ initialChampion, initialTab, initialLab, initialConfig }: {
  initialChampion?: string; initialTab?: Tab;
  /** Playstyle / role / bias seeds from the URL (album re-optimize, quick start). */
  initialConfig?: { playstyle?: string; role?: string; bias?: string };
  /** A flat loadout to open in the Custom Build Lab, from an album build. */
  initialLab?: { items: string[]; runes: string[] };
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
  // ?champion= arrives as a display NAME from every link that builds one
  // ("Vayne", "Kai'Sa"), and as a slug from anything that hand-wrote a URL.
  // Matching only slugs silently dropped the first kind and opened the studio
  // on whichever champion sorts first -- which the old /counter page did not
  // do, because it seeded its picker by name.
  const wanted = (initialChampion ?? "").toLowerCase();
  const initialSlug = champs.find(
    (entry) => entry.slug === wanted || entry.champion.name.toLowerCase() === wanted,
  )?.slug ?? champs[0]?.slug ?? "";
  const [slug, setSlug] = useState(initialSlug);
  const [tab, setTab] = useState<Tab>(initialTab ?? "generate");
  // Counted once per visit, not per switch: the question is how many people
  // ever see the lab, and a tab-flipper counting five times would answer a
  // different one.
  const labSeen = useRef(false);
  const [generatedAdvice, setGeneratedAdvice] = useState<Advice | null>(null);
  // A generated build handed to the Custom Build Lab so it can be run through
  // the damage check. The counter bumps on every send, and keys the Lab, so
  // sending the SAME build twice still reopens it rather than doing nothing.
  const [labSeed, setLabSeed] = useState<{ id: number; state: LabSeed } | null>(
    () => (initialLab ? { id: 0, state: labSeedFromFlat(initialLab.items, initialLab.runes) } : null));
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

  const name = rec.champion.name;

  // Two different controls, and most champions have neither: the header toggle
  // that swaps between separately generated build sets (Kayn), and the panel
  // toggle that re-reads stats and abilities in the transformed state.
  const tours = tabTours({
    formSets: forms.length > 1,
    transforms: Boolean(ultTransform(engineName)) || Boolean(DUAL_FORM_CHAMPIONS[engineName]),
    generated: Boolean(generatedAdvice && !generatedAdvice.error),
  });
  // Comparison targets are the curated variants, and that catalogue never
  // finished its review pass -- which is why the tab that served it is gone.
  // The gate it was behind stays: comparing against an unchecked build would
  // put the same unverified item list on screen through a different door.
  const comparisonChoices = builds && recommendedBuildsLive(rec.champion.name)
    ? variants.map((key) => comparableFromBuild(key, builds.builds[key]))
    : [];
  // The Lab seeds itself from the curated record, so it only opens for a
  // champion that has one. Both generators compute their answer live and work
  // for everyone.
  const availableTabs = builds ? TABS : TABS.filter((entry) => entry.id !== "customize");
  const effectiveTab = availableTabs.some((entry) => entry.id === tab) ? tab : "generate";
  useEffect(() => {
    if (effectiveTab === "customize" && !labSeen.current) {
      labSeen.current = true;
      track("custom_opened");
    }
  }, [effectiveTab]);

  const switchChamp = (s: string) => {
    setSlug(s);
    setFormKey("base");
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
        className="glass mb-2 w-full max-w-xs rounded-lg px-3 py-2 text-sm text-text outline-none focus:border-accent/50"
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
                    onClick={() => {
                      setFormKey(f.key);
                      // A generated build belongs to the form it was generated
                      // for. Keeping it across a toggle showed Rhaast's items
                      // beside Shadow Assassin's abilities, which is not a
                      // build anyone can play.
                      if (f.key !== formKeyState) setGeneratedAdvice(null);
                    }}
                    title={`${f.label}: its own items, runes and simulated damage`}
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
      {/* A grid, not a scrolling flex row. The row version put "Custom Build
          Lab" at x=377 on a 375px viewport -- entirely off-screen, with
          nothing to indicate the strip scrolled, so on a phone the tab may as
          well not have existed. Equal columns plus a short label per tab means
          all three fit and none of them needs discovering. */}
      <div
        data-tour="tabs"
        className={`glass mt-4 grid gap-1 rounded-xl p-1 ${availableTabs.length === 3 ? "grid-cols-3" : "grid-cols-2"}`}
      >
        {availableTabs.map((entry) => (
          <button
            key={entry.id}
            onClick={() => setTab(entry.id)}
            title={entry.help}
            className={`min-w-0 rounded-lg px-1.5 py-2 text-xs font-semibold transition sm:px-3 sm:text-sm ${effectiveTab === entry.id ? "bg-accent/20 text-accent" : "text-muted hover:text-text"}`}
          >
            <span className="sm:hidden">{entry.shortLabel}</span>
            <span className="hidden sm:inline">{entry.label}</span>
          </button>
        ))}
      </div>

      <div className="mt-4">
        {effectiveTab === "generate" && (
          <GenerateTab
            key={`${name}:${form?.key ?? "base"}`}
            name={name}
            championForm={form ? (form.key === "base" ? "shadow-assassin" : "rhaast") : undefined}
            advice={generatedAdvice}
            setAdvice={setGeneratedAdvice}
            onTestInLab={(seedState) => {
              setLabSeed({ id: Date.now(), state: seedState });
              setTab("customize");
            }}
            comparisonChoices={comparisonChoices}
            initialConfig={initialConfig}
          />
        )}
        {/* Keyed by champion so switching champions clears the enemy team and
            the build with it: the five picks you were up against belong to the
            game you were in, and carrying them onto a different champion would
            be an answer to a question nobody asked. */}
        {effectiveTab === "counter" && (
          <EnemyBuildAdvisor
            key={`counter:${name}:${form?.key ?? "base"}`}
            presetChampion={name}
            presetForm={form ? (form.key === "base" ? "shadow-assassin" : "rhaast") : undefined}
            mode="counter"
          />
        )}
        {effectiveTab === "customize" && builds && (
          <BuildCustomizer
            key={labSeed?.id ?? "empty"}
            name={engineName}
            data={builds}
            comparisonChoices={comparisonChoices}
            seed={labSeed?.state ?? null}
          />
        )}
      </div>

      {/* Hand-off between the two generators. Only shown from the one you are
          NOT on, and it switches tabs rather than navigating: they are two
          halves of the same question and both live on this page now. */}
      {effectiveTab !== "customize" && (
        <div className="mt-6" data-tour="counter-cta">
          {effectiveTab === "generate"
            ? <CounterBuilderCta onOpen={() => setTab("counter")} />
            : <GenerateBuildCta onGenerate={() => setTab("generate")} champion={name} />}
        </div>
      )}
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
    body: "Every ability recalculated against those stats, as real numbers rather than ratios. Tap one for the formula, the rank it is read at, and the cooldown after haste."
      + (transforms
        ? " The toggle here switches the whole panel to the transformed kit, so you can read the abilities and damage you actually get after transforming."
        : ""),
  },
];

/** What the open champion actually puts on screen. The tour describes only
 *  what is there: a step whose target does not exist still renders, just with
 *  nothing highlighted, and a walkthrough pointing at a control the player
 *  cannot see is worse than no step at all. */
type TourContext = { formSets: boolean; transforms: boolean; generated: boolean };

const tabTours = (ctx: TourContext): Record<Tab, { storageKey: string; steps: TourStep[] }> => ({
  // Moved here from the standalone /counter page. Two steps changed on the way:
  // the champion is chosen once by the studio's portrait strip rather than
  // inside this tab, and the step that explained how the counter builder
  // differs "from the Build Studio" was describing a page boundary that no
  // longer exists -- the contrast is now with the tab next to it.
  counter: {
    storageKey: "wtm_tour_counter_v3",
    steps: [
      {
        target: "enemy-team",
        title: "Tell it who you are up against",
        body: "Add up to five enemies. One is enough to get a build; the more you add, the more the item order shifts to handle their damage and their threats. This is the whole difference from the Personal Build Generator beside it, which never looks at the enemy.",
      },
      {
        target: "ally-team",
        optional: true,
        title: "Your team matters less, but it matters",
        body: "Allies mostly change whether you need to cover a gap yourself. If nobody on your side brings anti-heal or a front line, that lands on you, and the build shifts to reflect it.",
      },
      {
        target: "playstyle",
        title: "Adaptive, or commit to a plan",
        body: "Adaptive lets the enemy comp decide how you should play. Choose a specific playstyle instead when you already know what you want the game to look like, and the counter build is solved around that.",
      },
      {
        target: "role",
        title: "Where are you actually playing it?",
        body: "The role changes the build, not just the label: the same champion wants different first items in the jungle than in a solo lane. Pick something the champion is not normally played in and it warns you rather than quietly building something odd.",
      },
      {
        target: "objective",
        title: "Stats, synergy, or a balance of both",
        body: "Three options, and they trade against each other. Max stats favours the items whose raw stats this champion uses best per gold, accepting a bit less kit synergy. Max synergy favours items and runes that combo with the kit and with each other, even at some raw-stat cost. Balanced weighs both, and is the right answer more often than not.",
      },
      {
        target: "power-spike",
        title: "Say when you need to be strong",
        body: "Early, mid, late or balanced. Against a comp that wins late, spiking earlier is a real answer, and this changes the purchase order more than the item list.",
      },
      {
        target: "locks",
        optional: true,
        title: "Force in an item or rune you insist on",
        body: "Pin up to three items and two runes and the counter build has to include them. Skip it unless you already know one piece of the answer, say the enemy has heavy healing and you want the anti-heal locked in, and want the rest solved around it.",
      },
      {
        target: "generate",
        title: "Generate, then read the reasoning",
        body: "You get the optimal loadout in about 30 seconds. Items, runes and summoner spells sit open at the top because they are the build; everything under them starts folded, so tap Show to open it. Tap any item or rune for its cost, its stats and the reason it is there -- and against a known comp, the reasons name the enemies they answer.",
      },
      {
        target: "generate",
        title: "There is a guide for the build, too",
        body: "\"How to play this build\" is written for the loadout you just got rather than for the champion in general: what your first item buys you, when the build turns on, how to open the fight, and the mistake that wastes it against this comp.",
      },
    ],
  },
  generate: {
    storageKey: "wtm_tour_generate_v2",
    steps: [
      {
        target: "your-champion",
        title: "This build is about you, not the enemy",
        body: "The generator ignores who you are against on purpose. It builds around how you want to play the champion; the tab beside it, Build vs Enemy Team, is the one that reads the enemy team.",
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
        title: "Stats, synergy, or a balance of both",
        body: "Three options, and they trade against each other. Max stats favours the items whose raw stats this champion uses best per gold, accepting a bit less kit synergy. Max synergy favours items and runes that combo with the kit and with each other, even at some raw-stat cost. Balanced weighs both, and is the right answer more often than not.",
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
        body: "You get the full loadout in about 30 seconds, all in one card: item order with boot timing, the rune page, your summoner spells, and when the build spikes. Under it sit the swaps for games that go differently, then the guide; the deeper analysis stays folded until you want it.",
      },
      {
        target: "generate",
        title: "Read \"How to play this build\" before your game",
        body: "Under the build is a guide written for THIS loadout, not for the champion in general: what your first item buys you, the moment the build turns on, how the fight opens, and the mistake that wastes it. Underneath that, \"Why this build works\" explains every individual pick, and the evaluation rates the finished result.",
      },
      {
        target: "generate",
        title: "Tap anything you do not recognise",
        body: "Every item and rune in a generated build opens a card with its cost, its stats and the reason it was chosen for you. That works on a phone by tapping, not just by hovering.",
      },
      // The stats drawer only exists after a generation. Adding its step
      // before that would spotlight nothing, which is the thing this tour was
      // getting wrong; once a build is on screen it is worth explaining.
      ...(ctx.generated ? [{
        target: "stats-drawer",
        title: "The numbers, when you want them",
        body: "The full stat sheet and every ability's live value with this build, folded into one drawer. Stats is the whole build resolved onto the champion at level 15; Abilities recalculates each spell against those numbers. Guaranteed versus Fully scaled shows how greedy the build is."
          + (ctx.transforms ? " This champion transforms, so the toggles inside read either state." : ""),
      }] : []),
    ],
  },
  customize: {
    storageKey: "wtm_tour_lab_v2",
    steps: [
      {
        target: "lab-slots",
        title: "Five items, boots, and a full rune page",
        body: "Tap an empty slot to pick, tap the small cross to remove. Items, boots, keystone and the three minors all behave the same way.",
      },
      ...statSteps(ctx.transforms),
      {
        target: "lab-fight",
        title: "Send it into a fight",
        body: "Pick an opponent and press Fight. They stand on their own recommended build, so it is a real matchup rather than a target dummy, and you get time to kill, the combo, how many attacks landed, and where the damage came from. Nothing dodges or fights back, so read it as a damage check.",
      },
      {
        target: "lab-saved",
        title: "Save what you land on",
        body: "Custom builds are kept on this device, up to 20 of them, and can be compared against each other or against any recommended build. Signed in, you can file them into an album instead.",
      },
    ],
  },
});


function GenerateTab({
  name,
  championForm,
  advice,
  setAdvice,
  comparisonChoices,
  onTestInLab,
  initialConfig,
}: {
  name: string;
  championForm?: string;
  initialConfig?: { playstyle?: string; role?: string; bias?: string };
  advice: Advice | null;
  setAdvice: (advice: Advice | null) => void;
  comparisonChoices: ComparableBuild[];
  /** Hands this build to the Custom Build Lab so it can be run through the
   *  damage check. The generator has no fight of its own, and rebuilding the
   *  loadout by hand to test it was the only way across before. */
  onTestInLab: (seed: LabSeed) => void;
}) {
  const itemSlugs = advice && !advice.error
    ? [...(advice.items ?? []), ...(advice.bootsUpgrade ? [advice.bootsUpgrade] : advice.boots ? [advice.boots] : [])]
    : [];
  const runeNames = advice?.runes
    ? [advice.runes.keystone, ...advice.runes.minors, advice.runes.flex].filter(Boolean)
    : [];
  // Prefer the form the build was actually generated for, which the advisor
  // now reports back, and fall back to the form currently selected.
  const generatedForm =
    (advice?.requestMeta as { championForm?: string } | undefined)?.championForm || championForm;
  const panelName = formEngineName(name, generatedForm);
  // Which side of the analytical drawer is showing. Both panels stay mounted
  // so their internal toggles survive a tab flip.
  const [statsTab, setStatsTab] = useState<"stats" | "abilities">("stats");

  return (
    <div className="flex flex-col gap-4">
      <EnemyBuildAdvisor presetChampion={name} presetForm={championForm} mode="studio" initialConfig={initialConfig} onAdviceChange={setAdvice} deferFeedback />
      {itemSlugs.length > 0 && (
        <>
          {/* Build first, decisions second, explanation third -- and the raw
              numbers last, folded into one drawer so the page does not read
              as a report. */}
          <details className="glass group rounded-2xl p-4" data-tour="stats-drawer">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-2">
              <span className="min-w-0">
                <span className="block text-sm font-bold text-text">Build stats &amp; ability values</span>
                <span className="block text-xs font-normal text-faint">
                  The full stat sheet, and every ability&rsquo;s live numbers with this build
                </span>
              </span>
              <span aria-hidden className="shrink-0 text-accent transition group-open:rotate-180">⌄</span>
            </summary>
            <div className="mt-1 flex gap-1.5">
              {([["stats", "Stats"], ["abilities", "Abilities"]] as const).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setStatsTab(key)}
                  aria-pressed={statsTab === key}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                    statsTab === key
                      ? "bg-accent/15 text-accent ring-1 ring-accent/40"
                      : "bg-white/[0.04] text-muted hover:text-text"}`}
                >
                  {label}
                </button>
              ))}
            </div>
            {/* The FORM's kit, not the base champion's. These read `name` alone
                until now, so a build generated for Rhaast was displayed against
                Shadow Assassin's abilities and Shadow Assassin's base stats. */}
            <div className={statsTab === "stats" ? "" : "hidden"}>
              <BuildStatsPanel name={panelName} itemSlugs={itemSlugs} runeNames={runeNames} level={15} embedded />
            </div>
            <div className={statsTab === "abilities" ? "" : "hidden"}>
              <ChampionAbilitiesPanel name={panelName} itemSlugs={itemSlugs} runeNames={runeNames} level={15} embedded />
            </div>
          </details>
          <BuildComparison
            champion={name}
            current={{ id: "generated", label: "Generated build", itemSlugs, runeNames }}
            choices={comparisonChoices}
          />
          {/* The generator has no fight of its own; the Lab does. Rebuilding a
              generated loadout by hand to run it through the damage check was
              the only way across, which nobody was going to do. */}
          <button
            onClick={() => onTestInLab({
              items: [...(advice?.items ?? [])],
              // The Lab holds ONE boots slot. Send the tier-3 the build
              // actually finishes on, not the tier-2 it passes through.
              boots: advice?.bootsUpgrade || advice?.boots || "",
              runes: {
                keystone: advice?.runes?.keystone ?? "",
                tree: advice?.runes?.primaryTree ?? "Precision",
                minors: [
                  advice?.runes?.minors?.[0] ?? "",
                  advice?.runes?.minors?.[1] ?? "",
                  advice?.runes?.minors?.[2] ?? "",
                ],
                flex: advice?.runes?.flex ?? "",
              },
            })}
            className="glass glass-hover flex items-center justify-between gap-3 rounded-2xl border border-line p-4 text-left transition"
          >
            <span className="min-w-0">
              <span className="block text-sm font-bold text-text">
                Test this build in the Custom Build Lab
              </span>
              <span className="mt-0.5 block text-xs text-muted">
                Opens the loadout in the damage check, where you can fight a champion or
                a dummy, and swap pieces to see what actually changes.
              </span>
            </span>
            <span aria-hidden className="shrink-0 text-sm font-semibold text-accent">→</span>
          </button>
          <BuildFeedback champion={name} />
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
