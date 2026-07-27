"use client";

import { BuildTour, type TourStep } from "@/components/build-tour";

const COUNTER_TOUR: TourStep[] = [
  {
    target: "your-champion",
    title: "Start with what you are playing",
    body: "Pick your champion first. The role fills itself in from where that champion is normally played, and you can override it.",
  },
  {
    target: "enemy-team",
    title: "Then tell it who you are up against",
    body: "Add up to five enemies. One is enough to get a build; the more you add, the more the item order shifts to handle their damage and their threats. This is the whole difference from the Build Studio, which never looks at the enemy.",
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
    title: "Optimize for the job you need doing",
    body: "This is what the build is being solved FOR against this comp: carrying the fight, surviving the dive, or shredding the tank in front of you. It moves the item priorities rather than reshuffling the same list.",
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
    body: "You get the full loadout with a purchase order, boot timing, runes, situational swaps and a rating for the finished build. It takes about 30 seconds. Every item carries the reason it is there, and the reasons name the enemies they answer.",
  },
];

/** First-run tour for the Counter Builder. Skippable at every step.
 *
 *  Bumped to v2: the walkthrough covered four controls and skipped the ones
 *  that change the answer most, including the role and what the build is being
 *  optimized for. */
export function CounterTour() {
  return <BuildTour storageKey="wtm_tour_counter_v2" steps={COUNTER_TOUR} label="Tour" />;
}
