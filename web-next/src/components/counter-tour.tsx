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
    body: "Add up to five enemies. One is enough to get a build; the more you add, the more the item order shifts to handle their damage and their threats.",
  },
  {
    target: "locks",
    optional: true,
    title: "Force in an item or rune you insist on",
    body: "Pin up to three items and two runes and the counter build has to include them. Skip it unless you already know one piece of the answer -- say the enemy has heavy healing and you want the antiheal locked in -- and want the rest solved around it.",
  },
  {
    target: "generate",
    title: "Generate, then read the reasoning",
    body: "You get the full loadout with a purchase order, boot timing, runes, situational swaps and a rating for the finished build. It takes about 30 seconds.",
  },
];

/** First-run tour for the Counter Builder. Skippable at every step. */
export function CounterTour() {
  return <BuildTour storageKey="wtm_tour_counter_v1" steps={COUNTER_TOUR} label="Tour" />;
}
